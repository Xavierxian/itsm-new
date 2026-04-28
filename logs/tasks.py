from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from core.locks import cache_lock
from logs.models import AppLogIndex, LoginLog, OperationAuditLog, ResourceChangeLog, SecurityEventLog, TaskExecutionLog
from logs.utils import log_task_execution


@shared_task
def archive_expired_logs():
    with cache_lock("archive_expired_logs", timeout=1800) as acquired:
        if not acquired:
            result = {"skipped": True, "reason": "lock_not_acquired"}
            log_task_execution("archive_expired_logs", module="logs", parameters=result, result="warning")
            return result

        now = timezone.now()
        audit_cutoff = now - timedelta(days=settings.AUDIT_RETENTION_DAYS)
        app_cutoff = now - timedelta(days=settings.APP_LOG_RETENTION_DAYS)
        security_cutoff = now - timedelta(days=settings.SECURITY_EVENT_RETENTION_DAYS)

        deleted = {
            "login": LoginLog.objects.filter(occurred_at__lt=audit_cutoff).delete()[0],
            "audit": OperationAuditLog.objects.filter(occurred_at__lt=audit_cutoff).delete()[0],
            "resource": ResourceChangeLog.objects.filter(occurred_at__lt=audit_cutoff).delete()[0],
            "app": AppLogIndex.objects.filter(occurred_at__lt=app_cutoff).delete()[0],
            "task": TaskExecutionLog.objects.filter(occurred_at__lt=app_cutoff).delete()[0],
            "security": SecurityEventLog.objects.filter(occurred_at__lt=security_cutoff).delete()[0],
        }
        log_task_execution("archive_expired_logs", module="logs", parameters=deleted)
        return deleted
