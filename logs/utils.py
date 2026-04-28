from datetime import date, datetime
from decimal import Decimal

from core.middleware import get_current_user, get_request_trace_id
from core.network import get_access_ips
from core.security import is_sensitive_field, redact_mapping
from logs.models import AppLogIndex, LoginLog, OperationAuditLog, ResourceChangeLog, SecurityEventLog, TaskExecutionLog

AUDIT_FIELD_WHITELIST = {
    "assets.VirtualMachine": {
        "id",
        "host_ip",
        "vm_ip",
        "os_name",
        "os_version",
        "login_name",
        "remote_port",
        "cpu",
        "memory",
        "disk",
        "applicant",
        "department",
        "purpose",
        "environment",
        "open_date",
        "in_use",
        "end_date",
    },
    "assets.PhysicalHost": {
        "id",
        "server_ip",
        "model_name",
        "purchase_channel",
        "purchase_date",
        "port",
        "memory",
        "disk",
        "disk_type",
        "memory_used",
        "disk_used",
        "memory_remaining",
        "disk_remaining",
        "remaining_capacity",
        "department",
        "purpose",
    },
    "assets.QualificationManagement": {
        "id",
        "qualification_category",
        "belong_entity",
        "belong_department",
        "qualification_name",
        "manager",
        "usage",
        "cost",
        "account",
        "status",
        "expire_date",
        "remark",
        "supplier_name",
        "last_update_time",
        "create_time",
    },
}


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def serialize_instance(instance):
    data = {}
    whitelist = AUDIT_FIELD_WHITELIST.get(instance._meta.label)
    for field in instance._meta.fields:
        if whitelist is not None and field.name not in whitelist:
            continue
        if is_sensitive_field(field.name):
            continue
        value = getattr(instance, field.name)
        if hasattr(field, "attname") and field.attname != field.name:
            value = getattr(instance, field.attname)
        if isinstance(value, (datetime, date)):
            data[field.name] = value.isoformat()
        elif isinstance(value, Decimal):
            data[field.name] = float(value)
        else:
            data[field.name] = value
    return data


def log_login_attempt(request, success, user=None, username="", failure_reason=""):
    private_ip, public_ip, _ = get_access_ips()
    LoginLog.objects.create(
        user=user,
        username=username or getattr(user, "username", ""),
        success=success,
        ip_address=get_client_ip(request),
        private_ip=private_ip if private_ip != "-" else None,
        public_ip=public_ip if public_ip != "-" else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
        failure_reason=failure_reason,
        trace_id=getattr(request, "trace_id", get_request_trace_id()),
    )


def log_operation(user=None, module="", action="", target=None, request=None, result="success"):
    snapshot = {}
    path = ""
    method = ""
    trace_id = get_request_trace_id()
    if request is not None:
        path = request.path
        method = request.method
        trace_id = getattr(request, "trace_id", trace_id)
        snapshot = redact_mapping({key: value for key, value in request.POST.items()})
    OperationAuditLog.objects.create(
        user=user,
        module=module,
        action=action,
        target_type=target._meta.label if target else "",
        target_id=str(target.pk) if target else "",
        target_display=str(target) if target else "",
        request_path=path,
        method=method,
        request_snapshot=snapshot,
        result=result,
        trace_id=trace_id,
    )


def log_resource_change_by_type(
    resource_type,
    resource_id,
    action,
    before_snapshot=None,
    after_snapshot=None,
    changed_fields=None,
):
    ResourceChangeLog.objects.create(
        actor=get_current_user() if getattr(get_current_user(), "is_authenticated", False) else None,
        resource_type=resource_type,
        resource_id=str(resource_id),
        action=action,
        changed_fields=changed_fields or [],
        before_snapshot=before_snapshot or {},
        after_snapshot=after_snapshot or {},
        trace_id=get_request_trace_id(),
    )


def log_resource_change(instance, action, before_snapshot=None, after_snapshot=None, changed_fields=None):
    log_resource_change_by_type(
        resource_type=instance._meta.label,
        resource_id=instance.pk,
        action=action,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        changed_fields=changed_fields,
    )


def log_security_event(event_type, severity, description, request=None, user=None, username=""):
    SecurityEventLog.objects.create(
        user=user,
        username=username or getattr(user, "username", ""),
        event_type=event_type,
        severity=severity,
        ip_address=get_client_ip(request) if request else None,
        description=description,
        status=SecurityEventLog.ProcessStatusChoices.RESOLVED,
        trace_id=getattr(request, "trace_id", get_request_trace_id()) if request else get_request_trace_id(),
    )


def log_application_event(module, summary, level=AppLogIndex.LevelChoices.INFO, details="", trace_id=""):
    AppLogIndex.objects.create(
        module=module,
        level=level,
        summary=summary,
        details=details,
        trace_id=trace_id or get_request_trace_id(),
    )


def log_task_execution(task_name, module="", parameters=None, result="success", error_summary="", duration_ms=0):
    TaskExecutionLog.objects.create(
        task_name=task_name,
        module=module,
        parameters=redact_mapping(parameters or {}),
        result=result,
        error_summary=error_summary,
        duration_ms=duration_ms,
        trace_id=get_request_trace_id(),
    )
