import json
import logging
import os
import socket
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import connection
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from accounts.models import Role, User
from assets.models import Namespace, PhysicalHost, QualificationManagement, VirtualMachine
from bsecp.models import AuthorizationRecord, Module
from bsecp.sqlserver_auth import fetch_authorization_record_trend
from core.cache_helpers import cache_delete, cache_get, cache_set
from logs.models import LoginLog, OperationAuditLog, ResourceChangeLog, SecurityEventLog
from logs.utils import log_operation
from mappings.models import DNSRecord, PortMapping
from monitoring.models import ScheduledTaskRecord

logger = logging.getLogger(__name__)

AUTH_RESULT_SUCCESS_VALUES = ("success", "成功", "自动化授权成功")
AUTH_RESULT_FAILURE_VALUES = ("fail", "失败", "自动化授权失败")
_PROCESS_START_TS = time.time()


def cached_count(cache_key, queryset, ttl=60):
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        value = queryset.count()
    except Exception:
        logger.warning("Failed to count queryset for cache key %s; fallback to 0", cache_key)
        value = 0
    cache_set(cache_key, value, timeout=ttl)
    return value


def _db_health_status():
    started_at = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        latency_ms = (time.perf_counter() - started_at) * 1000
        return {
            "ok": True,
            "status_text": "正常",
            "tone_class": "is-success",
            "detail": f"数据库连接可用（延迟 {latency_ms:.1f} ms）",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        latency_ms = (time.perf_counter() - started_at) * 1000
        return {
            "ok": False,
            "status_text": "异常",
            "tone_class": "is-danger",
            "detail": f"数据库连接失败：{str(exc)[:90]}（耗时 {latency_ms:.1f} ms）",
            "latency_ms": latency_ms,
        }


def _redis_health_status():
    redis_url = str(getattr(settings, "REDIS_URL", "") or "").strip()
    if not redis_url:
        return {
            "ok": True,
            "status_text": "未启用",
            "tone_class": "is-warning",
            "detail": "未配置 Redis，当前使用本地缓存",
            "latency_ms": None,
        }

    probe_key = f"health:redis:probe:{int(time.time())}:{os.getpid()}"
    probe_value = f"ok-{os.getpid()}"
    started_at = time.perf_counter()
    try:
        wrote = cache_set(probe_key, probe_value, timeout=20)
        current = cache_get(probe_key)
        cache_delete(probe_key)
    except Exception as exc:
        latency_ms = (time.perf_counter() - started_at) * 1000
        return {
            "ok": False,
            "status_text": "异常",
            "tone_class": "is-danger",
            "detail": f"Redis 探针失败：{str(exc)[:90]}（耗时 {latency_ms:.1f} ms）",
            "latency_ms": latency_ms,
        }

    latency_ms = (time.perf_counter() - started_at) * 1000
    if wrote and current == probe_value:
        return {
            "ok": True,
            "status_text": "正常",
            "tone_class": "is-success",
            "detail": f"Redis 读写探针成功（延迟 {latency_ms:.1f} ms）",
            "latency_ms": latency_ms,
        }
    return {
        "ok": False,
        "status_text": "异常",
        "tone_class": "is-danger",
        "detail": f"Redis 探针失败，请检查连通性或认证配置（耗时 {latency_ms:.1f} ms）",
        "latency_ms": latency_ms,
    }


def _system_health_status(db_ok, redis_ok):
    uptime_seconds = max(1, int(time.time() - _PROCESS_START_TS))
    uptime_minutes = uptime_seconds // 60
    if db_ok and redis_ok:
        return {
            "status_text": "正常",
            "tone_class": "is-success",
            "detail": f"服务运行中（{socket.gethostname()}，进程运行 {uptime_minutes} 分钟）",
        }
    if db_ok and not redis_ok:
        return {
            "status_text": "降级",
            "tone_class": "is-warning",
            "detail": "应用可用，但 Redis 异常会影响限流/缓存能力",
        }
    return {
        "status_text": "异常",
        "tone_class": "is-danger",
        "detail": "存在关键依赖异常，请立即排查",
    }


def build_system_health_cards():
    db_status = _db_health_status()
    redis_status = _redis_health_status()
    system_status = _system_health_status(db_ok=db_status["ok"], redis_ok=redis_status["ok"])
    checked_at = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")

    return [
        {
            "label": "系统运行状态",
            "status_text": system_status["status_text"],
            "tone_class": system_status["tone_class"],
            "detail": f"{system_status['detail']}（检测时间：{checked_at}）",
        },
        {
            "label": "数据库连接",
            "status_text": db_status["status_text"],
            "tone_class": db_status["tone_class"],
            "detail": db_status["detail"],
        },
        {
            "label": "Redis 连接",
            "status_text": redis_status["status_text"],
            "tone_class": redis_status["tone_class"],
            "detail": redis_status["detail"],
        },
    ]


class HomeRedirectView(TemplateView):
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:dashboard")
        return redirect("accounts:login")


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ttl = int(getattr(settings, "DASHBOARD_STATS_CACHE_TTL", 60))
        context["stats"] = [
            {"label": "用户", "value": cached_count("dash:stats:users", User.objects, ttl=ttl)},
            {"label": "角色", "value": cached_count("dash:stats:roles", Role.objects, ttl=ttl)},
            {"label": "虚拟机", "value": cached_count("dash:stats:vms", VirtualMachine.objects, ttl=ttl)},
            {"label": "物理机", "value": cached_count("dash:stats:hosts", PhysicalHost.objects, ttl=ttl)},
            {"label": "端口映射", "value": cached_count("dash:stats:ports", PortMapping.objects, ttl=ttl)},
            {"label": "域名映射", "value": cached_count("dash:stats:dns", DNSRecord.objects, ttl=ttl)},
            {"label": "授权记录", "value": cached_count("dash:stats:auth", AuthorizationRecord.objects, ttl=ttl)},
            {"label": "资质卡片", "value": cached_count("dash:stats:qualification_cards", QualificationManagement.objects, ttl=ttl)},
        ]
        context["recent_logs"] = OperationAuditLog.objects.select_related("user")[:8]
        context["alerts"] = SecurityEventLog.objects.filter(status=SecurityEventLog.ProcessStatusChoices.OPEN)[:6]
        context["quick_links"] = [
            {"label": "用户管理", "url": reverse("accounts:user-list")},
            {"label": "资产管理", "url": reverse("assets:vm-list")},
            {"label": "日志中心", "url": reverse("logs:dashboard")},
            {"label": "授权管理", "url": reverse("bsecp:authorization-list")},
        ]
        context["module_counts"] = [
            {"label": "虚拟机", "value": cached_count("dash:stats:vms", VirtualMachine.objects, ttl=ttl)},
            {"label": "物理机", "value": cached_count("dash:stats:hosts", PhysicalHost.objects, ttl=ttl)},
            {"label": "NameSpace", "value": cached_count("dash:stats:namespace", Namespace.objects, ttl=ttl)},
            {"label": "模块", "value": cached_count("dash:stats:module", Module.objects, ttl=ttl)},
            {"label": "登录日志", "value": cached_count("dash:stats:loginlog", LoginLog.objects, ttl=ttl)},
            {"label": "审计日志", "value": cached_count("dash:stats:resource_change", ResourceChangeLog.objects, ttl=ttl)},
            {"label": "任务记录", "value": cached_count("dash:stats:scheduled_task", ScheduledTaskRecord.objects, ttl=ttl)},
        ]
        context["monitoring_alerts_api_url"] = reverse("monitoring:host-resource-alerts-api")
        context["monitoring_alert_notify_api_url"] = reverse("monitoring:host-resource-alert-notify-api")
        context["monitoring_targets_api_url"] = reverse("monitoring:host-resource-targets-api")
        context["monitoring_default_alert_threshold"] = 90
        context["monitoring_refresh_seconds"] = 45
        context["health_cards"] = build_system_health_cards()

        trend_series = []
        try:
            trend_series = fetch_authorization_record_trend(
                days=30,
                success_values=AUTH_RESULT_SUCCESS_VALUES,
                failure_values=AUTH_RESULT_FAILURE_VALUES,
            )
        except Exception:
            logger.exception("Failed to load BSECP authorization trend for dashboard.")

        context["bsecp_auth_trend_json"] = json.dumps(
            {
                "series": trend_series,
                "periods": {
                    "week": 7,
                    "half_month": 15,
                    "month": 30,
                },
            },
            ensure_ascii=False,
        )
        return context


class PlaceholderView(LoginRequiredMixin, TemplateView):
    template_name = "core/placeholder.html"
    page_title = "功能占位"
    description = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        context["description"] = self.description
        return context


class SearchableListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    template_name = "core/generic_list.html"
    paginate_by = 10
    paginate_by_options = [10, 20, 50]
    search_fields = []
    columns = []
    page_title = ""
    page_description = ""
    create_url_name = ""
    edit_url_name = ""
    show_actions = True
    panel_css_class = ""
    color_result_field = ""
    result_success_values = ()
    result_failure_values = ()

    def build_list_url(self, **query_updates):
        params = self.request.GET.copy()
        params.pop("page", None)
        for key, value in query_updates.items():
            if value in (None, ""):
                params.pop(key, None)
            else:
                params[key] = str(value)
        query = params.urlencode()
        return f"{self.request.path}?{query}" if query else self.request.path

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if query and self.search_fields:
            filters = Q()
            for field in self.search_fields:
                filters |= Q(**{f"{field}__icontains": query})
            queryset = queryset.filter(filters)
        return queryset

    def get_paginate_by(self, queryset):
        default = self.paginate_by
        per_page_raw = self.request.GET.get("per_page", "").strip()
        if not per_page_raw:
            return default
        try:
            per_page = int(per_page_raw)
        except ValueError:
            return default
        if per_page in self.paginate_by_options:
            return per_page
        return default

    def _resolve_attr(self, obj, accessor):
        value = obj
        for part in accessor.split("."):
            value = getattr(value, part)
            if callable(value):
                value = value()
        return value

    def _normalize_result_value(self, value):
        if value is None:
            return ""
        return str(value).strip().lower()

    def _resolve_result_tone(self, accessor, value):
        if not self.color_result_field or accessor != self.color_result_field:
            return ""
        normalized = self._normalize_result_value(value)
        success_set = {self._normalize_result_value(v) for v in self.result_success_values}
        failure_set = {self._normalize_result_value(v) for v in self.result_failure_values}
        if normalized in success_set:
            return "success"
        if normalized in failure_set:
            return "danger"
        return ""

    def get_rows(self, object_list):
        rows = []
        for obj in object_list:
            cells = []
            values = []
            for _, accessor in self.columns:
                value = self._resolve_attr(obj, accessor)
                values.append(value)
                cells.append(
                    {
                        "accessor": accessor,
                        "value": value,
                        "tone": self._resolve_result_tone(accessor, value),
                    }
                )
            rows.append(
                {
                    "object": obj,
                    "values": values,
                    "cells": cells,
                    "edit_url": reverse(self.edit_url_name, kwargs={"pk": obj.pk}) if self.show_actions and self.edit_url_name else "",
                }
            )
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        context["page_description"] = self.page_description
        context["query"] = self.request.GET.get("q", "")
        search_params = self.request.GET.copy()
        search_params.pop("q", None)
        search_params.pop("page", None)
        per_page_params = self.request.GET.copy()
        per_page_params.pop("per_page", None)
        per_page_params.pop("page", None)
        pagination_params = self.request.GET.copy()
        pagination_params.pop("page", None)
        context["search_hidden_pairs"] = [(key, value) for key, values in search_params.lists() for value in values]
        context["per_page_hidden_pairs"] = [(key, value) for key, values in per_page_params.lists() for value in values]
        context["pagination_query"] = pagination_params.urlencode()
        context["paginate_by_options"] = self.paginate_by_options
        context["current_per_page"] = self.get_paginate_by(self.object_list)
        context["columns"] = [label for label, _ in self.columns]
        context["rows"] = self.get_rows(context["object_list"])
        context["create_url"] = reverse(self.create_url_name) if self.create_url_name else ""
        context["show_actions"] = self.show_actions
        context["empty_colspan"] = len(self.columns) + (1 if self.show_actions else 0)
        context["panel_css_class"] = self.panel_css_class
        return context


class ManagedCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    template_name = "core/generic_form.html"
    page_title = ""
    success_url = None

    def form_valid(self, form):
        if hasattr(form.instance, "created_by") and not form.instance.created_by_id:
            form.instance.created_by = self.request.user
        if hasattr(form.instance, "updated_by"):
            form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        log_operation(
            user=self.request.user,
            module=self.model._meta.app_label,
            action="create",
            target=self.object,
            request=self.request,
            result="success",
        )
        messages.success(self.request, f"{self.model._meta.verbose_name}创建成功。")
        return response

    def get_success_url(self):
        return self.success_url or reverse_lazy("core:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        context["submit_label"] = "保存"
        return context


class ManagedUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    template_name = "core/generic_form.html"
    page_title = ""
    success_url = None

    def form_valid(self, form):
        if hasattr(form.instance, "updated_by"):
            form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        log_operation(
            user=self.request.user,
            module=self.model._meta.app_label,
            action="update",
            target=self.object,
            request=self.request,
            result="success",
        )
        messages.success(self.request, f"{self.model._meta.verbose_name}更新成功。")
        return response

    def get_success_url(self):
        return self.success_url or reverse_lazy("core:dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        context["submit_label"] = "更新"
        return context
