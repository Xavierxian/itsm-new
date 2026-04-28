from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, Q
from django.utils import timezone
from django.views.generic import ListView, TemplateView

from core.network import split_private_public_ips
from logs.models import AppLogIndex, LoginLog, OperationAuditLog, ResourceChangeLog, SecurityEventLog, TaskExecutionLog


MODULE_LABELS = {
    "accounts": "系统管理",
    "assets": "资产管理",
    "mappings": "映射管理",
    "bsecp": "BSECP",
    "cloudops": "行云管家",
    "monitoring": "运维监控",
    "logs": "日志管理",
    "core": "系统概览",
}

PATH_LABELS = {
    "/accounts/users/": "系统管理 / 用户管理",
    "/accounts/roles/": "系统管理 / 角色管理",
    "/accounts/password/": "账户中心 / 修改密码",
    "/mappings/ports/": "映射管理 / 端口映射",
    "/mappings/domains/": "映射管理 / 域名映射",
    "/assets/virtual-machines/": "资产管理 / 虚拟机",
    "/assets/physical-hosts/": "资产管理 / 物理机",
    "/assets/namespaces/": "资产管理 / NameSpace",
    "/bsecp/modules/": "BSECP / 模块管理",
    "/bsecp/authorizations/": "BSECP / 授权管理",
    "/monitoring/targets/": "运维监控 / 主机监控",
    "/monitoring/tasks/": "运维监控 / 定时任务",
    "/logs/login/": "日志管理 / 登录日志",
    "/logs/audit/": "日志管理 / 操作审计",
    "/logs/app/": "日志管理 / 应用日志",
    "/logs/tasks/": "日志管理 / 任务日志",
    "/logs/changes/": "日志管理 / 资源变更",
    "/logs/security/": "日志管理 / 安全事件",
}

ACTION_LABELS = {
    "create": "新建了",
    "update": "修改了",
    "delete": "删除了",
    "login": "登录了系统",
    "logout": "退出了系统",
    "change_password": "修改了密码",
    "created": "创建了",
    "updated": "更新了",
    "deleted": "删除了",
}

RESULT_LABELS = {
    "success": "成功",
    "failed": "失败",
    "failure": "失败",
    "error": "错误",
    "warning": "警告",
    "info": "信息",
}

CHANGE_BADGE_LABELS = {
    "created": "新增",
    "updated": "修改",
    "deleted": "删除",
    "create": "新增",
    "update": "修改",
    "delete": "删除",
}

FIELD_LABELS = {
    "username": "用户名",
    "full_name": "姓名",
    "email": "邮箱",
    "phone_number": "手机号",
    "status": "状态",
    "roles": "角色",
    "password": "密码",
    "interface": "网络接口",
    "protocol": "协议",
    "public_ip": "公网 IP",
    "public_port": "公网端口",
    "private_ip": "内网 IP",
    "private_port": "内网端口",
    "domain": "域名",
    "record_type": "记录类型",
    "target": "目标值",
    "environment": "环境",
    "description": "说明",
    "name": "名称",
    "host_ip": "主机IP",
    "vm_ip": "虚拟机IP",
    "os_name": "操作系统",
    "os_version": "系统版本",
    "login_name": "登录名",
    "remote_port": "远程端口",
    "cpu": "CPU",
    "memory": "内存",
    "disk": "硬盘",
    "applicant": "申请人",
    "department": "部门",
    "purpose": "用途",
    "open_date": "开通日期",
    "in_use": "是否在用",
    "end_date": "结束日期",
    "permissions": "权限",
    "data_scope": "数据范围",
    "updated_at": "更新时间",
    "created_at": "创建时间",
}

RESOURCE_TYPE_LABELS = {
    "accounts.User": "用户",
    "accounts.Role": "角色",
    "assets.VirtualMachine": "虚拟机",
    "assets.PhysicalHost": "物理机",
    "assets.Namespace": "NameSpace",
    "mappings.PortMapping": "端口映射",
    "mappings.DomainMapping": "域名映射",
    "bsecp.Module": "模块",
    "bsecp.AuthorizationRecord": "授权记录",
}

RESOURCE_MENU_LABELS = {
    "accounts.User": "系统管理 / 用户管理",
    "accounts.Role": "系统管理 / 角色管理",
    "assets.VirtualMachine": "资产管理 / 虚拟机",
    "assets.PhysicalHost": "资产管理 / 物理机",
    "assets.Namespace": "资产管理 / NameSpace",
    "mappings.PortMapping": "映射管理 / 端口映射",
    "mappings.DomainMapping": "映射管理 / 域名映射",
    "bsecp.Module": "BSECP / 模块管理",
    "bsecp.AuthorizationRecord": "BSECP / 授权管理",
}


def _module_label(module):
    return MODULE_LABELS.get(module, module or "未知模块")


def _path_label(path):
    if not path:
        return ""
    for prefix, label in PATH_LABELS.items():
        if path.startswith(prefix):
            return label
    return path


def _resource_type_label(resource_type):
    return RESOURCE_TYPE_LABELS.get(resource_type, resource_type or "资源对象")


def _resource_menu_label(resource_type):
    return RESOURCE_MENU_LABELS.get(resource_type, _resource_type_label(resource_type))


def _action_label(action):
    return ACTION_LABELS.get(action, action or "执行了操作")


def _result_label(result):
    return RESULT_LABELS.get((result or "").lower(), result or "-")


def _tone_from_result(result):
    value = (result or "").lower()
    if value in {"success", "resolved", "active"}:
        return "success"
    if value in {"warning", "medium", "in_progress"}:
        return "warning"
    if value in {"error", "failed", "failure", "critical", "high", "open"}:
        return "danger"
    return "neutral"


def _safe_actor(user, fallback="系统"):
    if user:
        return getattr(user, "full_name", "") or getattr(user, "username", "") or str(user)
    return fallback


def _field_label(name):
    return FIELD_LABELS.get(name, name)


def _format_value(value):
    if value in (None, "", [], {}):
        return "-"
    if isinstance(value, list):
        return "、".join(str(item) for item in value) or "-"
    if isinstance(value, dict):
        return " / ".join(f"{key}: {val}" for key, val in value.items()) or "-"
    return str(value)


def _format_snapshot_target(snapshot, fallback=""):
    if not snapshot:
        return fallback or "-"

    if all(key in snapshot for key in ("public_ip", "public_port", "private_ip", "private_port")):
        return (
            f"{snapshot.get('public_ip')}:{snapshot.get('public_port')} -> "
            f"{snapshot.get('private_ip')}:{snapshot.get('private_port')}"
        )

    if snapshot.get("domain") and snapshot.get("target"):
        return f"{snapshot.get('domain')} -> {snapshot.get('target')}"

    if snapshot.get("username"):
        return snapshot.get("username")

    for key in ("name", "title", "domain"):
        if snapshot.get(key):
            return str(snapshot.get(key))

    return fallback or "-"


def _build_detail(label, value):
    return {"label": label, "value": value}


def _format_occurred_at(value):
    if not value:
        return "-"
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S")


def _simplify_user_agent(user_agent):
    ua = (user_agent or "").lower()
    if not ua:
        return "-"

    os_name = "未知系统"
    browser_name = "未知浏览器"

    if "windows nt 10.0" in ua:
        os_name = "Windows 10"
    elif "windows nt 11.0" in ua:
        os_name = "Windows 11"
    elif "windows" in ua:
        os_name = "Windows"
    elif "mac os x" in ua or "macintosh" in ua:
        os_name = "macOS"
    elif "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "ipad" in ua or "ios" in ua:
        os_name = "iOS"
    elif "linux" in ua:
        os_name = "Linux"

    if "edg/" in ua:
        browser_name = "Edge"
    elif "chrome/" in ua and "edg/" not in ua:
        browser_name = "Chrome"
    elif "firefox/" in ua:
        browser_name = "Firefox"
    elif "safari/" in ua and "chrome/" not in ua:
        browser_name = "Safari"

    return f"{os_name} / {browser_name}"


def build_operation_audit_entry(obj):
    area = _path_label(obj.request_path) or _module_label(obj.module)
    action_text = _action_label(obj.action)
    target_text = obj.target_display or _format_snapshot_target(obj.request_snapshot, obj.target_id or "目标对象")

    if obj.action == "login":
        summary = f"{_safe_actor(obj.user)} 登录了系统。"
    elif obj.action == "logout":
        summary = f"{_safe_actor(obj.user)} 退出了系统。"
    elif obj.action == "change_password":
        summary = f"{_safe_actor(obj.user)} 在“{area}”中修改了账号密码。"
    else:
        summary = f"{_safe_actor(obj.user)} 在“{area}”中{action_text}“{target_text}”。"

    details = [
        _build_detail("操作人", _safe_actor(obj.user)),
        _build_detail("所属菜单", area),
        _build_detail("请求方式", obj.method or "-"),
        _build_detail("请求路径", obj.request_path or "-"),
        _build_detail("处理结果", _result_label(obj.result)),
    ]
    if obj.target_type:
        details.append(_build_detail("对象类型", _resource_type_label(obj.target_type)))
    if obj.target_id:
        details.append(_build_detail("对象 ID", obj.target_id))
    if obj.request_snapshot:
        touched_fields = "、".join(_field_label(key) for key in obj.request_snapshot.keys())
        details.append(_build_detail("提交字段", touched_fields))
    if obj.trace_id:
        details.append(_build_detail("追踪 ID", obj.trace_id))

    return {
        "category": "操作审计日志",
        "title": area,
        "summary": summary,
        "meta": f"{_format_occurred_at(obj.occurred_at)} · { _safe_actor(obj.user) }",
        "badge": _result_label(obj.result),
        "tone": _tone_from_result(obj.result),
        "details": details,
    }


def build_login_entry(obj):
    fallback_private, fallback_public = split_private_public_ips(obj.ip_address or "")
    private_ip = obj.private_ip or fallback_private or "-"
    public_ip = obj.public_ip or fallback_public or "-"
    summary = f"账号“{obj.username}”发起登录，内网 IP 为 {private_ip}，公网出口 IP 为 {public_ip}。"
    if obj.success:
        summary += " 登录成功。"
    else:
        summary += " 登录失败。"

    details = [
        _build_detail("账号", obj.username or "-"),
        _build_detail("登录结果", "成功" if obj.success else "失败"),
        _build_detail("内网 IP", private_ip),
        _build_detail("公网出口 IP", public_ip),
    ]
    if obj.failure_reason:
        details.append(_build_detail("失败原因", obj.failure_reason))
    if obj.user_agent:
        details.append(_build_detail("客户端", _simplify_user_agent(obj.user_agent)))
    if obj.trace_id:
        details.append(_build_detail("追踪 ID", obj.trace_id))

    return {
        "category": "登录日志",
        "title": "登录成功" if obj.success else "登录失败",
        "summary": summary,
        "meta": f"{_format_occurred_at(obj.occurred_at)} · {obj.username or '-'}",
        "badge": "成功" if obj.success else "失败",
        "tone": "success" if obj.success else "danger",
        "details": details,
    }


def build_app_log_entry(obj):
    details = [
        _build_detail("日志级别", obj.get_level_display()),
        _build_detail("所属模块", _module_label(obj.module)),
    ]
    if obj.details:
        details.append(_build_detail("详细信息", obj.details))
    if obj.trace_id:
        details.append(_build_detail("追踪 ID", obj.trace_id))

    return {
        "category": "应用日志",
        "title": f"{obj.get_level_display()} · {_module_label(obj.module)}",
        "summary": obj.summary,
        "meta": _format_occurred_at(obj.occurred_at),
        "badge": obj.get_level_display(),
        "tone": _tone_from_result(obj.level),
        "details": details,
    }


def build_task_entry(obj):
    summary = f"任务“{obj.task_name}”执行{_result_label(obj.result)}，耗时 {obj.duration_ms} ms。"
    if obj.error_summary:
        summary += f" 错误摘要：{obj.error_summary}"

    details = [
        _build_detail("任务名称", obj.task_name),
        _build_detail("所属模块", _module_label(obj.module) if obj.module else "-"),
        _build_detail("执行结果", _result_label(obj.result)),
        _build_detail("耗时", f"{obj.duration_ms} ms"),
    ]
    if obj.parameters:
        details.append(_build_detail("任务参数", _format_value(obj.parameters)))
    if obj.trace_id:
        details.append(_build_detail("追踪 ID", obj.trace_id))

    return {
        "category": "任务执行日志",
        "title": obj.task_name,
        "summary": summary,
        "meta": _format_occurred_at(obj.occurred_at),
        "badge": _result_label(obj.result),
        "tone": _tone_from_result(obj.result),
        "details": details,
    }


def build_resource_change_entry(obj):
    area = _resource_menu_label(obj.resource_type)
    resource_label = _resource_type_label(obj.resource_type)
    after_target = _format_snapshot_target(obj.after_snapshot)
    before_target = _format_snapshot_target(obj.before_snapshot)
    target_text = after_target if after_target != "-" else before_target
    action_text = _action_label(obj.action)

    summary = f"{_safe_actor(obj.actor)} 在“{area}”中{action_text}“{target_text}”。"
    if obj.changed_fields:
        summary += f" 变更字段：{'、'.join(_field_label(field) for field in obj.changed_fields)}。"

    details = [
        _build_detail("操作人", _safe_actor(obj.actor)),
        _build_detail("所属菜单", area),
        _build_detail("资源类型", resource_label),
        _build_detail("资源 ID", obj.resource_id),
    ]
    if obj.changed_fields:
        details.append(_build_detail("变更字段", "、".join(_field_label(field) for field in obj.changed_fields)))

    change_rows = []
    for field in obj.changed_fields[:8]:
        before_value = _format_value(obj.before_snapshot.get(field))
        after_value = _format_value(obj.after_snapshot.get(field))
        change_rows.append(
            _build_detail(_field_label(field), f"{before_value} -> {after_value}")
        )

    if obj.trace_id:
        details.append(_build_detail("追踪 ID", obj.trace_id))

    return {
        "category": "资源变更日志",
        "title": f"{resource_label} · {_action_label(obj.action)}",
        "summary": summary,
        "meta": f"{_format_occurred_at(obj.occurred_at)} · {_safe_actor(obj.actor)}",
        "badge": CHANGE_BADGE_LABELS.get(obj.action, obj.action),
        "tone": "success" if obj.action in {"created", "create"} else "warning" if obj.action in {"updated", "update"} else "danger" if obj.action in {"deleted", "delete"} else "neutral",
        "details": details,
        "change_rows": change_rows,
    }


def build_security_entry(obj):
    details = [
        _build_detail("安全时间", _format_occurred_at(obj.occurred_at)),
        _build_detail("账号", obj.username or _safe_actor(obj.user, "匿名")),
        _build_detail("事件级别", obj.get_severity_display()),
        _build_detail("来源 IP", obj.ip_address or "-"),
    ]
    if obj.trace_id:
        details.append(_build_detail("追踪 ID", obj.trace_id))

    return {
        "category": "安全事件日志",
        "title": obj.get_event_type_display(),
        "summary": obj.description,
        "meta": f"{_format_occurred_at(obj.occurred_at)} · {obj.username or _safe_actor(obj.user, '匿名')}",
        "badge": "已记录",
        "tone": _tone_from_result(obj.severity),
        "details": details,
    }


class LogsDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "logs/dashboard.html"
    permission_required = "logs.view_operationauditlog"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cards"] = [
            {"label": "登录日志", "value": LoginLog.objects.count()},
            {"label": "操作审计", "value": OperationAuditLog.objects.count()},
            {"label": "应用日志", "value": AppLogIndex.objects.count()},
            {"label": "任务日志", "value": TaskExecutionLog.objects.count()},
            {"label": "资源变更", "value": ResourceChangeLog.objects.count()},
            {"label": "安全事件", "value": SecurityEventLog.objects.count()},
        ]
        severity_label_map = dict(SecurityEventLog.SeverityChoices.choices)
        severity_order = [
            SecurityEventLog.SeverityChoices.CRITICAL,
            SecurityEventLog.SeverityChoices.HIGH,
            SecurityEventLog.SeverityChoices.MEDIUM,
            SecurityEventLog.SeverityChoices.LOW,
        ]
        severity_tone_map = {
            SecurityEventLog.SeverityChoices.CRITICAL: "critical",
            SecurityEventLog.SeverityChoices.HIGH: "high",
            SecurityEventLog.SeverityChoices.MEDIUM: "medium",
            SecurityEventLog.SeverityChoices.LOW: "low",
        }
        severity_counts = {
            item["severity"]: item["total"]
            for item in SecurityEventLog.objects.values("severity").annotate(total=Count("id"))
        }
        security_total = sum(severity_counts.values())
        dominant_severity = None
        if security_total:
            dominant_severity = max(severity_order, key=lambda severity: severity_counts.get(severity, 0))
        context["security_breakdown_total"] = security_total
        context["security_breakdown_dominant"] = severity_label_map.get(dominant_severity, "")
        context["security_breakdown"] = [
            {
                "key": severity,
                "severity": severity_label_map.get(severity, severity),
                "tone": severity_tone_map.get(severity, "medium"),
                "total": severity_counts.get(severity, 0),
                "percentage": (severity_counts.get(severity, 0) / security_total * 100) if security_total else 0,
            }
            for severity in severity_order
        ]
        recent_audits = OperationAuditLog.objects.select_related("user")[:6]
        context["recent_audit_entries"] = [build_operation_audit_entry(log) for log in recent_audits]
        return context


class BaseLogListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    template_name = "logs/list.html"
    paginate_by = 15
    page_title = ""
    page_description = ""
    permission_required = ""
    category_label = ""
    search_placeholder = "搜索日志关键字"
    filter_name = ""
    filter_options = []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["page_title"] = self.page_title
        context["page_description"] = self.page_description
        context["category_label"] = self.category_label
        context["query"] = self.request.GET.get("q", "")
        context["search_placeholder"] = self.search_placeholder
        context["filter_name"] = self.filter_name
        context["filter_options"] = self.filter_options
        context["current_filter"] = self.request.GET.get(self.filter_name, "") if self.filter_name else ""
        context["entries"] = self.build_entries(context["object_list"])
        context["pagination_query"] = query_params.urlencode()
        context["total_count"] = context["page_obj"].paginator.count if context.get("page_obj") else len(context["entries"])
        return context

    def build_entries(self, object_list):
        return []


class LoginLogListView(BaseLogListView):
    model = LoginLog
    permission_required = "logs.view_loginlog"
    page_title = "登录日志"
    page_description = "按时间查看账号登录成功、失败、来源 IP 以及失败原因。"
    category_label = "登录日志中心"
    search_placeholder = "搜索账号"

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(username__icontains=query)
        return queryset

    def build_entries(self, object_list):
        return [build_login_entry(obj) for obj in object_list]


class OperationAuditLogListView(BaseLogListView):
    model = OperationAuditLog
    permission_required = "logs.view_operationauditlog"
    page_title = "操作审计日志"
    page_description = "记录用户在哪个菜单中对什么对象执行了什么操作，以及最终处理结果。"
    category_label = "审计追踪"
    search_placeholder = "搜索模块、动作、对象"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("user")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(module__icontains=query)
                | Q(action__icontains=query)
                | Q(target_display__icontains=query)
                | Q(request_path__icontains=query)
            )
        return queryset

    def build_entries(self, object_list):
        return [build_operation_audit_entry(obj) for obj in object_list]


class AppLogListView(BaseLogListView):
    model = AppLogIndex
    permission_required = "logs.view_applogindex"
    page_title = "应用日志"
    page_description = "查看应用运行摘要、告警信息和异常追踪。"
    category_label = "应用运行"
    search_placeholder = "搜索模块或摘要"
    filter_name = "level"
    filter_options = [
        ("info", "信息"),
        ("warning", "警告"),
        ("error", "错误"),
        ("critical", "严重"),
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        level = self.request.GET.get("level", "").strip()
        query = self.request.GET.get("q", "").strip()
        if level:
            queryset = queryset.filter(level=level)
        if query:
            queryset = queryset.filter(Q(summary__icontains=query) | Q(module__icontains=query))
        return queryset

    def build_entries(self, object_list):
        return [build_app_log_entry(obj) for obj in object_list]


class TaskExecutionLogListView(BaseLogListView):
    model = TaskExecutionLog
    permission_required = "logs.view_taskexecutionlog"
    page_title = "任务执行日志"
    page_description = "查看定时任务和后台任务的执行结果、参数与耗时。"
    category_label = "任务执行"
    search_placeholder = "搜索任务名称"

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(task_name__icontains=query)
        return queryset

    def build_entries(self, object_list):
        return [build_task_entry(obj) for obj in object_list]


class ResourceChangeLogListView(BaseLogListView):
    model = ResourceChangeLog
    permission_required = "logs.view_resourcechangelog"
    page_title = "资源变更日志"
    page_description = "逐条记录资源对象的创建、修改、删除，以及变更字段的前后差异。"
    category_label = "资源变更"
    search_placeholder = "搜索资源类型、字段、资源 ID"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("actor")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(resource_type__icontains=query)
                | Q(resource_id__icontains=query)
                | Q(changed_fields__icontains=query)
            )
        return queryset

    def build_entries(self, object_list):
        return [build_resource_change_entry(obj) for obj in object_list]


class SecurityEventLogListView(BaseLogListView):
    model = SecurityEventLog
    permission_required = "logs.view_securityeventlog"
    page_title = "安全事件日志"
    page_description = "查看异常登录、越权访问和敏感操作等安全事件及处置状态。"
    category_label = "安全事件"
    search_placeholder = "搜索账号、描述"
    filter_name = "severity"
    filter_options = [
        ("low", "低"),
        ("medium", "中"),
        ("high", "高"),
        ("critical", "严重"),
    ]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("user")
        severity = self.request.GET.get("severity", "").strip()
        query = self.request.GET.get("q", "").strip()
        if severity:
            queryset = queryset.filter(severity=severity)
        if query:
            queryset = queryset.filter(Q(description__icontains=query) | Q(username__icontains=query))
        return queryset

    def build_entries(self, object_list):
        return [build_security_entry(obj) for obj in object_list]
