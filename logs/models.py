from django.conf import settings
from django.db import models


class LoginLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="login_logs",
    )
    username = models.CharField(max_length=150, verbose_name="登录账号")
    success = models.BooleanField(default=False, verbose_name="是否成功")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="本地请求地址")
    private_ip = models.GenericIPAddressField(blank=True, null=True, verbose_name="内网IP")
    public_ip = models.GenericIPAddressField(blank=True, null=True, verbose_name="公网出口IP")
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="客户端")
    failure_reason = models.CharField(max_length=255, blank=True, verbose_name="失败原因")
    trace_id = models.CharField(max_length=32, blank=True, verbose_name="追踪ID")
    occurred_at = models.DateTimeField(auto_now_add=True, verbose_name="发生时间")

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "登录日志"
        verbose_name_plural = "登录日志"
        indexes = [
            models.Index(fields=["occurred_at"], name="idx_loginlog_occurred"),
            models.Index(fields=["username", "occurred_at"], name="idx_loginlog_user_time"),
            models.Index(fields=["success", "occurred_at"], name="idx_loginlog_success_time"),
        ]

    def __str__(self):
        return f"{self.username} - {'成功' if self.success else '失败'}"


class OperationAuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    module = models.CharField(max_length=50, verbose_name="模块")
    action = models.CharField(max_length=50, verbose_name="动作")
    target_type = models.CharField(max_length=120, blank=True, verbose_name="对象类型")
    target_id = models.CharField(max_length=50, blank=True, verbose_name="对象ID")
    target_display = models.CharField(max_length=255, blank=True, verbose_name="对象展示值")
    request_path = models.CharField(max_length=255, blank=True, verbose_name="请求路径")
    method = models.CharField(max_length=10, blank=True, verbose_name="请求方法")
    request_snapshot = models.JSONField(default=dict, blank=True, verbose_name="请求摘要")
    result = models.CharField(max_length=30, default="success", verbose_name="结果")
    trace_id = models.CharField(max_length=32, blank=True, verbose_name="追踪ID")
    occurred_at = models.DateTimeField(auto_now_add=True, verbose_name="发生时间")

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "操作审计日志"
        verbose_name_plural = "操作审计日志"
        indexes = [
            models.Index(fields=["occurred_at"], name="idx_audit_occurred"),
            models.Index(fields=["module", "occurred_at"], name="idx_audit_module_time"),
            models.Index(fields=["result", "occurred_at"], name="idx_audit_result_time"),
        ]


class AppLogIndex(models.Model):
    class LevelChoices(models.TextChoices):
        INFO = "info", "INFO"
        WARNING = "warning", "WARNING"
        ERROR = "error", "ERROR"
        CRITICAL = "critical", "CRITICAL"

    level = models.CharField(max_length=20, choices=LevelChoices.choices, default=LevelChoices.INFO, verbose_name="级别")
    module = models.CharField(max_length=50, verbose_name="模块")
    trace_id = models.CharField(max_length=32, blank=True, verbose_name="追踪ID")
    summary = models.CharField(max_length=255, verbose_name="摘要")
    details = models.TextField(blank=True, verbose_name="详情")
    occurred_at = models.DateTimeField(auto_now_add=True, verbose_name="发生时间")

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "应用日志"
        verbose_name_plural = "应用日志"
        indexes = [
            models.Index(fields=["occurred_at"], name="idx_applog_occurred"),
            models.Index(fields=["module", "occurred_at"], name="idx_applog_module_time"),
            models.Index(fields=["level", "occurred_at"], name="idx_applog_level_time"),
        ]


class TaskExecutionLog(models.Model):
    task_name = models.CharField(max_length=120, verbose_name="任务名称")
    module = models.CharField(max_length=50, blank=True, verbose_name="模块")
    parameters = models.JSONField(default=dict, blank=True, verbose_name="参数")
    result = models.CharField(max_length=30, default="success", verbose_name="执行结果")
    error_summary = models.CharField(max_length=255, blank=True, verbose_name="错误摘要")
    duration_ms = models.PositiveIntegerField(default=0, verbose_name="耗时(ms)")
    trace_id = models.CharField(max_length=32, blank=True, verbose_name="追踪ID")
    occurred_at = models.DateTimeField(auto_now_add=True, verbose_name="发生时间")

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "任务执行日志"
        verbose_name_plural = "任务执行日志"
        indexes = [
            models.Index(fields=["occurred_at"], name="idx_tasklog_occurred"),
            models.Index(fields=["task_name", "occurred_at"], name="idx_tasklog_name_time"),
            models.Index(fields=["result", "occurred_at"], name="idx_tasklog_result_time"),
        ]


class ResourceChangeLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="resource_changes",
    )
    resource_type = models.CharField(max_length=120, verbose_name="资源类型")
    resource_id = models.CharField(max_length=50, verbose_name="资源ID")
    action = models.CharField(max_length=30, verbose_name="动作")
    changed_fields = models.JSONField(default=list, blank=True, verbose_name="变更字段")
    before_snapshot = models.JSONField(default=dict, blank=True, verbose_name="变更前")
    after_snapshot = models.JSONField(default=dict, blank=True, verbose_name="变更后")
    trace_id = models.CharField(max_length=32, blank=True, verbose_name="追踪ID")
    occurred_at = models.DateTimeField(auto_now_add=True, verbose_name="发生时间")

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "资源变更日志"
        verbose_name_plural = "资源变更日志"
        indexes = [
            models.Index(fields=["occurred_at"], name="idx_change_occurred"),
            models.Index(fields=["resource_type", "occurred_at"], name="idx_change_type_time"),
            models.Index(fields=["resource_id", "occurred_at"], name="idx_change_id_time"),
        ]


class SecurityEventLog(models.Model):
    class EventTypeChoices(models.TextChoices):
        ABNORMAL_LOGIN = "abnormal_login", "异常登录"
        LOCKOUT = "lockout", "账号锁定"
        PRIVILEGE_VIOLATION = "privilege_violation", "越权访问"
        SENSITIVE_ACTION = "sensitive_action", "敏感操作"

    class SeverityChoices(models.TextChoices):
        LOW = "low", "低"
        MEDIUM = "medium", "中"
        HIGH = "high", "高"
        CRITICAL = "critical", "严重"

    class ProcessStatusChoices(models.TextChoices):
        OPEN = "open", "待处理"
        IN_PROGRESS = "in_progress", "处理中"
        RESOLVED = "resolved", "已关闭"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="security_events",
    )
    username = models.CharField(max_length=150, blank=True, verbose_name="账号")
    event_type = models.CharField(max_length=50, choices=EventTypeChoices.choices, verbose_name="事件类型")
    severity = models.CharField(max_length=20, choices=SeverityChoices.choices, default=SeverityChoices.MEDIUM, verbose_name="等级")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="IP地址")
    description = models.CharField(max_length=255, verbose_name="描述")
    status = models.CharField(
        max_length=20,
        choices=ProcessStatusChoices.choices,
        default=ProcessStatusChoices.RESOLVED,
        verbose_name="处理状态",
    )
    trace_id = models.CharField(max_length=32, blank=True, verbose_name="追踪ID")
    occurred_at = models.DateTimeField(auto_now_add=True, verbose_name="发生时间")

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "安全事件日志"
        verbose_name_plural = "安全事件日志"
        indexes = [
            models.Index(fields=["occurred_at"], name="idx_sec_event_occurred"),
            models.Index(fields=["status", "severity", "occurred_at"], name="idx_sec_status_sev_time"),
            models.Index(fields=["username", "occurred_at"], name="idx_sec_user_time"),
        ]
