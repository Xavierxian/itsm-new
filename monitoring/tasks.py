from __future__ import annotations

import time

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from core.locks import cache_lock
from logs.utils import log_task_execution
from monitoring.email_notifier import AlertEmailNotifierError, alert_email_notifier
from monitoring.models import ScheduledTaskRecord
from monitoring.services import MonitoringServiceError, build_host_alerts, fetch_host_snapshot


def _to_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@shared_task(name="monitoring.send_daily_partition_alert_email")
def send_daily_partition_alert_email() -> dict[str, object]:
    with cache_lock("monitoring_send_daily_partition_alert_email", timeout=3600) as acquired:
        if not acquired:
            payload = {"skipped": True, "reason": "lock_not_acquired"}
            log_task_execution(
                task_name="send_daily_partition_alert_email",
                module="monitoring",
                parameters=payload,
                result=ScheduledTaskRecord.ResultChoices.PARTIAL,
                duration_ms=1,
            )
            return payload

        started_at = time.perf_counter()
        task_name = "send_daily_partition_alert_email"
        hour = _to_int(getattr(settings, "MONITORING_DAILY_ALERT_EMAIL_HOUR", 9), 9)
        minute = _to_int(getattr(settings, "MONITORING_DAILY_ALERT_EMAIL_MINUTE", 0), 0)
        schedule_text = f"{minute} {hour} * * *"
        threshold = _to_float(getattr(settings, "MONITORING_DAILY_ALERT_THRESHOLD", 90.0), 90.0)

        task_record, _ = ScheduledTaskRecord.objects.get_or_create(
            name=task_name,
            defaults={"schedule": schedule_text},
        )
        if task_record.schedule != schedule_text:
            task_record.schedule = schedule_text

        result: str = ScheduledTaskRecord.ResultChoices.SUCCESS
        excerpt = ""
        payload: dict[str, object] = {}

        try:
            snapshot = fetch_host_snapshot()
            alerts = build_host_alerts(snapshot.get("hosts", []), threshold=threshold)
            payload["threshold"] = threshold
            payload["total_hosts"] = len(alerts)
            payload["total_alerts"] = sum(len(item.get("alerts", [])) for item in alerts)

            if not alerts:
                excerpt = f"09:00 自动发送已跳过：没有达到 {threshold:.1f}% 阈值的分区告警。"
                payload["sent"] = False
                payload["reason"] = "no_alerts"
                return payload

            email_result = alert_email_notifier.send_partition_alert_email(
                alerts,
                threshold=threshold,
                requested_recipients=None,
                fallback_user_email="",
            )
            payload.update(email_result)
            payload["sent"] = True

            failed_count = len(email_result.get("failed_recipients") or [])
            if failed_count > 0:
                result = ScheduledTaskRecord.ResultChoices.PARTIAL
                excerpt = (
                    f"已发送 {email_result.get('sent_count', 0)} 封，"
                    f"失败 {failed_count} 封，告警主机 {email_result.get('host_count', 0)} 台。"
                )
            else:
                excerpt = (
                    f"已发送 {email_result.get('sent_count', 0)} 封，"
                    f"覆盖告警主机 {email_result.get('host_count', 0)} 台。"
                )

            return payload
        except (MonitoringServiceError, AlertEmailNotifierError) as exc:
            result = ScheduledTaskRecord.ResultChoices.FAILED
            excerpt = str(exc)[:240]
            payload["error"] = str(exc)
            raise
        except Exception as exc:  # pragma: no cover
            result = ScheduledTaskRecord.ResultChoices.FAILED
            excerpt = f"任务执行异常: {exc}"[:240]
            payload["error"] = str(exc)
            raise
        finally:
            duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
            task_record.last_run_at = timezone.now()
            task_record.last_duration_ms = duration_ms
            task_record.last_result = result
            task_record.log_excerpt = excerpt[:255]
            task_record.save(
                update_fields=[
                    "schedule",
                    "last_run_at",
                    "last_duration_ms",
                    "last_result",
                    "log_excerpt",
                    "updated_at",
                ]
            )
            log_task_execution(
                task_name=task_name,
                module="monitoring",
                parameters=payload,
                result=result,
                error_summary=excerpt if result != ScheduledTaskRecord.ResultChoices.SUCCESS else "",
                duration_ms=duration_ms,
            )
