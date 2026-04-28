from django.db import models

from core.models import ManagedModel


class MonitoringTarget(ManagedModel):
    class TargetTypeChoices(models.TextChoices):
        HOST = "host", "主机"
        K8S = "k8s", "K8S"
        SERVICE = "service", "服务"

    name = models.CharField(max_length=120, unique=True, verbose_name="监控对象")
    target_type = models.CharField(max_length=20, choices=TargetTypeChoices.choices, default=TargetTypeChoices.HOST, verbose_name="类型")
    endpoint = models.CharField(max_length=160, blank=True, verbose_name="地址")
    last_heartbeat_at = models.DateTimeField(blank=True, null=True, verbose_name="最近心跳")
    description = models.CharField(max_length=255, blank=True, verbose_name="说明")

    class Meta:
        ordering = ["name"]
        verbose_name = "监控对象"
        verbose_name_plural = "监控对象"

    def __str__(self):
        return self.name


class ScheduledTaskRecord(ManagedModel):
    class ResultChoices(models.TextChoices):
        SUCCESS = "success", "成功"
        FAILED = "failed", "失败"
        PARTIAL = "partial", "部分成功"

    name = models.CharField(max_length=120, unique=True, verbose_name="任务名称")
    schedule = models.CharField(max_length=80, verbose_name="调度表达式")
    last_run_at = models.DateTimeField(blank=True, null=True, verbose_name="最近执行时间")
    last_duration_ms = models.PositiveIntegerField(default=0, verbose_name="最近耗时(ms)")
    last_result = models.CharField(max_length=20, choices=ResultChoices.choices, default=ResultChoices.SUCCESS, verbose_name="最近结果")
    log_excerpt = models.CharField(max_length=255, blank=True, verbose_name="日志摘要")

    class Meta:
        ordering = ["name"]
        verbose_name = "定时任务"
        verbose_name_plural = "定时任务"

    def __str__(self):
        return self.name
