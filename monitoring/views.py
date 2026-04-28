from __future__ import annotations

import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import JsonResponse, StreamingHttpResponse
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from core.views import SearchableListView
from monitoring.email_notifier import AlertEmailNotifierError, alert_email_notifier
from monitoring.models import MonitoringTarget, ScheduledTaskRecord
from monitoring.services import (
    MonitoringServiceError,
    analyze_k8s_filtered_data,
    build_host_alerts,
    fetch_host_snapshot,
    fetch_host_trend,
    fetch_k8s_namespace_latest,
    fetch_k8s_node_trend,
    fetch_k8s_namespace_trend,
    fetch_k8s_nodes_latest,
    fetch_k8s_summary,
    fetch_prometheus_targets,
    stream_k8s_node_analysis,
    stream_k8s_namespace_analysis,
)

logger = logging.getLogger(__name__)


class HostResourceDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "monitoring/host_resource_dashboard.html"
    permission_required = "monitoring.view_monitoringtarget"
    page_title = "主机资源监控"
    page_description = "实时查看主机 CPU、内存、磁盘与告警信息，并支持单机趋势分析。"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": self.page_title,
                "page_description": self.page_description,
                "default_alert_threshold": 90,
                "default_refresh_seconds": 45,
                "api_data_url": reverse("monitoring:host-resource-data-api"),
                "api_alerts_url": reverse("monitoring:host-resource-alerts-api"),
                "api_targets_url": reverse("monitoring:host-resource-targets-api"),
                "api_trend_url_template": reverse(
                    "monitoring:host-resource-trend-api",
                    kwargs={"instance": "__INSTANCE__"},
                ),
            }
        )
        return context


class K8SResourceDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "monitoring/k8s_resource_dashboard.html"
    permission_required = "monitoring.view_monitoringtarget"
    page_title = "K8S 资源监控"
    page_description = "集中查看 K8S 集群总览、命名空间利用率、节点负载和命名空间趋势。"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": self.page_title,
                "page_description": self.page_description,
                "default_refresh_seconds": 60,
                "default_trend_hours": 24,
                "api_summary_url": reverse("monitoring:k8s-summary-api"),
                "api_namespaces_url": reverse("monitoring:k8s-namespaces-api"),
                "api_nodes_url": reverse("monitoring:k8s-nodes-api"),
                "api_trend_url_template": reverse(
                    "monitoring:k8s-namespace-trend-api",
                    kwargs={"namespace": "__NAMESPACE__"},
                ),
                "api_node_trend_url_template": reverse(
                    "monitoring:k8s-node-trend-api",
                    kwargs={"node_ip": "__NODE__"},
                ),
                "api_ai_stream_url_template": reverse(
                    "monitoring:k8s-analysis-stream-api",
                    kwargs={"namespace": "__NAMESPACE__"},
                ),
                "api_node_ai_stream_url_template": reverse(
                    "monitoring:k8s-node-analysis-stream-api",
                    kwargs={"node_ip": "__NODE__"},
                ),
            }
        )
        return context


class MonitoringAPIViewBase(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "monitoring.view_monitoringtarget"

    def _json_ok(self, payload: dict | None = None, *, status: int = 200) -> JsonResponse:
        body = {"success": True}
        if payload:
            body.update(payload)
        return JsonResponse(body, status=status)

    def _json_error(self, message: str, *, status: int = 400, details: str = "") -> JsonResponse:
        body = {"success": False, "error": message}
        if details:
            body["details"] = details[:600]
        return JsonResponse(body, status=status)


class HostResourceDataAPIView(MonitoringAPIViewBase):
    def get(self, request, *args, **kwargs):
        try:
            snapshot = fetch_host_snapshot()
        except MonitoringServiceError as exc:
            return self._json_error("主机监控数据获取失败", status=502, details=str(exc))
        except Exception:
            logger.exception("Unexpected error while fetching host monitoring snapshot")
            return self._json_error("服务内部错误", status=500)

        hosts = snapshot.get("hosts", [])
        return self._json_ok(
            {
                "hosts": hosts,
                "metrics": snapshot.get("metric_definitions", []),
                "errors": snapshot.get("errors", []),
                "total_hosts": len(hosts),
            }
        )


class HostResourceAlertsAPIView(MonitoringAPIViewBase):
    def get(self, request, *args, **kwargs):
        threshold_raw = request.GET.get("threshold", "90").strip()
        try:
            threshold = float(threshold_raw)
        except ValueError:
            return self._json_error("threshold 参数必须为数字", status=400)

        if threshold < 0 or threshold > 100:
            return self._json_error("threshold 参数范围应为 0-100", status=400)

        try:
            snapshot = fetch_host_snapshot()
            alerts = build_host_alerts(snapshot.get("hosts", []), threshold=threshold)
        except MonitoringServiceError as exc:
            return self._json_error("告警数据获取失败", status=502, details=str(exc))
        except Exception:
            logger.exception("Unexpected error while fetching host alerts")
            return self._json_error("服务内部错误", status=500)

        return self._json_ok(
            {
                "threshold": threshold,
                "alerts": alerts,
                "total_hosts": len(alerts),
                "total_alerts": sum(len(item.get("alerts", [])) for item in alerts),
            }
        )


class HostResourceAlertNotifyAPIView(MonitoringAPIViewBase):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            return self._json_error("请求体必须是合法 JSON", status=400)

        threshold_raw = str(payload.get("threshold", "90")).strip()
        try:
            threshold = float(threshold_raw)
        except ValueError:
            return self._json_error("threshold 参数必须为数字", status=400)

        if threshold < 0 or threshold > 100:
            return self._json_error("threshold 参数范围应为 0-100", status=400)

        recipients_payload = payload.get("recipients")

        try:
            snapshot = fetch_host_snapshot()
            alerts = build_host_alerts(snapshot.get("hosts", []), threshold=threshold)
        except MonitoringServiceError as exc:
            return self._json_error("告警数据获取失败", status=502, details=str(exc))
        except Exception:
            logger.exception("Unexpected error while preparing host alerts for email")
            return self._json_error("服务内部错误", status=500)

        if not alerts:
            return self._json_error("当前没有达到阈值的分区告警，无需发送邮件。", status=400)

        try:
            result = alert_email_notifier.send_partition_alert_email(
                alerts,
                threshold=threshold,
                requested_recipients=recipients_payload,
                fallback_user_email=getattr(request.user, "email", ""),
            )
        except AlertEmailNotifierError as exc:
            return self._json_error(str(exc), status=400)
        except Exception:
            logger.exception("Unexpected error while sending host alert email")
            return self._json_error("邮件发送失败，请稍后重试。", status=500)

        return self._json_ok(
            {
                "message": (
                    f"邮件发送成功，已发送至 {len(result.get('recipients', []))} 个收件人，"
                    f"覆盖 {result.get('host_count', 0)} 台告警主机。"
                ),
                "sent_at": result.get("sent_at", ""),
                "recipients": result.get("recipients", []),
                "host_count": result.get("host_count", 0),
                "alert_count": result.get("alert_count", 0),
            }
        )


class HostResourceTrendAPIView(MonitoringAPIViewBase):
    def get(self, request, instance: str, *args, **kwargs):
        range_key = request.GET.get("range", "1h").strip() or "1h"

        try:
            trend = fetch_host_trend(instance, range_key=range_key)
        except MonitoringServiceError as exc:
            return self._json_error("主机趋势数据获取失败", status=502, details=str(exc))
        except Exception:
            logger.exception("Unexpected error while fetching host trend")
            return self._json_error("服务内部错误", status=500)

        return self._json_ok({"trend": trend})


class HostResourceTargetsAPIView(MonitoringAPIViewBase):
    def get(self, request, *args, **kwargs):
        try:
            targets = fetch_prometheus_targets()
        except MonitoringServiceError as exc:
            return self._json_error("采集目标状态获取失败", status=502, details=str(exc))
        except Exception:
            logger.exception("Unexpected error while fetching prometheus targets")
            return self._json_error("服务内部错误", status=500)

        return self._json_ok(
            {
                "targets": targets,
                "total": len(targets),
                "healthy": sum(1 for target in targets if target.get("health") == "up"),
            }
        )


class K8SSummaryAPIView(MonitoringAPIViewBase):
    def get(self, request, *args, **kwargs):
        try:
            summary = fetch_k8s_summary()
        except MonitoringServiceError as exc:
            return self._json_error("K8S汇总数据获取失败", status=502, details=str(exc))
        except Exception:
            logger.exception("Unexpected error while fetching K8S summary")
            return self._json_error("服务内部错误", status=500)
        return self._json_ok(summary)


class K8SNamespacesAPIView(MonitoringAPIViewBase):
    def get(self, request, *args, **kwargs):
        hours_raw = request.GET.get("hours", "24").strip()
        try:
            hours = int(hours_raw)
        except ValueError:
            return self._json_error("hours 参数必须为整数", status=400)

        try:
            namespaces = fetch_k8s_namespace_latest(hours=hours)
        except MonitoringServiceError as exc:
            return self._json_error("命名空间监控数据获取失败", status=502, details=str(exc))
        except Exception:
            logger.exception("Unexpected error while fetching K8S namespaces")
            return self._json_error("服务内部错误", status=500)

        return self._json_ok({"namespaces": namespaces, "total": len(namespaces), "hours": hours})


class K8SNodesAPIView(MonitoringAPIViewBase):
    def get(self, request, *args, **kwargs):
        hours_raw = request.GET.get("hours", "24").strip()
        try:
            hours = int(hours_raw)
        except ValueError:
            return self._json_error("hours 参数必须为整数", status=400)

        try:
            nodes = fetch_k8s_nodes_latest(hours=hours)
        except MonitoringServiceError as exc:
            return self._json_error("节点监控数据获取失败", status=502, details=str(exc))
        except Exception:
            logger.exception("Unexpected error while fetching K8S nodes")
            return self._json_error("服务内部错误", status=500)

        return self._json_ok({"nodes": nodes, "total": len(nodes), "hours": hours})


class K8SNamespaceTrendAPIView(MonitoringAPIViewBase):
    def get(self, request, namespace: str, *args, **kwargs):
        hours_raw = request.GET.get("hours", "24").strip()
        try:
            hours = int(hours_raw)
        except ValueError:
            return self._json_error("hours 参数必须为整数", status=400)

        try:
            trend = fetch_k8s_namespace_trend(namespace=namespace, hours=hours)
        except MonitoringServiceError as exc:
            return self._json_error("命名空间趋势获取失败", status=502, details=str(exc))
        except Exception:
            logger.exception("Unexpected error while fetching K8S namespace trend")
            return self._json_error("服务内部错误", status=500)

        return self._json_ok({"trend": trend})


class K8SNodeTrendAPIView(MonitoringAPIViewBase):
    def get(self, request, node_ip: str, *args, **kwargs):
        hours_raw = request.GET.get("hours", "24").strip()
        try:
            hours = int(hours_raw)
        except ValueError:
            return self._json_error("hours 参数必须为整数", status=400)

        try:
            trend = fetch_k8s_node_trend(node_ip=node_ip, hours=hours)
        except MonitoringServiceError as exc:
            return self._json_error("节点趋势获取失败", status=502, details=str(exc))
        except Exception:
            logger.exception("Unexpected error while fetching K8S node trend")
            return self._json_error("服务内部错误", status=500)

        return self._json_ok({"trend": trend})


class K8SAnalysisAPIView(MonitoringAPIViewBase):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            return self._json_error("请求体必须是合法 JSON", status=400)

        try:
            analysis = analyze_k8s_filtered_data(payload)
        except MonitoringServiceError as exc:
            return self._json_error("AI分析失败", status=502, details=str(exc))
        except Exception:
            logger.exception("Unexpected error while analyzing K8S filtered data")
            return self._json_error("服务内部错误", status=500)

        return self._json_ok({"analysis": analysis})


class K8SNamespaceAnalysisStreamAPIView(MonitoringAPIViewBase):
    http_method_names = ["get"]

    def get(self, request, namespace: str, *args, **kwargs):
        hours_raw = request.GET.get("hours", "24").strip()
        try:
            hours = int(hours_raw)
        except ValueError:
            return self._json_error("hours 参数必须为整数", status=400)

        namespace_text = str(namespace or "").strip()
        if not namespace_text:
            return self._json_error("namespace 参数不能为空", status=400)

        def stream_generator():
            try:
                for piece in stream_k8s_namespace_analysis(namespace_text, hours=hours):
                    if piece:
                        yield piece
            except MonitoringServiceError as exc:
                yield f"分析失败: {exc}"
            except Exception:
                logger.exception("Unexpected error while streaming K8S namespace analysis")
                yield "分析失败: 服务内部错误"

        response = StreamingHttpResponse(stream_generator(), content_type="text/plain; charset=utf-8")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate, no-transform, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        response["X-Accel-Buffering"] = "no"
        return response


class K8SNodeAnalysisStreamAPIView(MonitoringAPIViewBase):
    http_method_names = ["get"]

    def get(self, request, node_ip: str, *args, **kwargs):
        hours_raw = request.GET.get("hours", "24").strip()
        try:
            hours = int(hours_raw)
        except ValueError:
            return self._json_error("hours 参数必须为整数", status=400)

        node_ip_text = str(node_ip or "").strip()
        if not node_ip_text:
            return self._json_error("node_ip 参数不能为空", status=400)

        def stream_generator():
            try:
                for piece in stream_k8s_node_analysis(node_ip_text, hours=hours):
                    if piece:
                        yield piece
            except MonitoringServiceError as exc:
                yield f"分析失败: {exc}"
            except Exception:
                logger.exception("Unexpected error while streaming K8S node analysis")
                yield "分析失败: 服务内部错误"

        response = StreamingHttpResponse(stream_generator(), content_type="text/plain; charset=utf-8")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate, no-transform, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        response["X-Accel-Buffering"] = "no"
        return response


class MonitoringTargetListView(SearchableListView):
    model = MonitoringTarget
    permission_required = "monitoring.view_monitoringtarget"
    page_title = "主机 / K8S 资源监控"
    page_description = "展示已纳管的主机、K8S 和服务监控对象。"
    search_fields = ["name", "endpoint"]
    columns = [("名称", "name"), ("类型", "get_target_type_display"), ("地址", "endpoint"), ("状态", "get_status_display")]


class ScheduledTaskRecordListView(SearchableListView):
    model = ScheduledTaskRecord
    permission_required = "monitoring.view_scheduledtaskrecord"
    page_title = "定时任务监控"
    page_description = "集中查看调度任务最近执行结果和日志摘要。"
    search_fields = ["name", "schedule", "log_excerpt"]
    columns = [("名称", "name"), ("调度", "schedule"), ("最近结果", "get_last_result_display"), ("状态", "get_status_display")]
