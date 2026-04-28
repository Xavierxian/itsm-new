from django.conf import settings
from django.db import models


class StatusChoices(models.TextChoices):
    ACTIVE = "active", "启用"
    INACTIVE = "inactive", "停用"
    MAINTENANCE = "maintenance", "维护中"
    ARCHIVED = "archived", "已归档"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        abstract = True


class ManagedModel(TimeStampedModel):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="%(class)s_created",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="创建人",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="%(class)s_updated",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="更新人",
    )
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.ACTIVE,
        verbose_name="状态",
    )

    class Meta:
        abstract = True


class Notification(TimeStampedModel):
    class LevelChoices(models.TextChoices):
        INFO = "info", "信息"
        WARNING = "warning", "警告"
        CRITICAL = "critical", "严重"

    title = models.CharField(max_length=120, verbose_name="标题")
    content = models.TextField(verbose_name="内容")
    level = models.CharField(max_length=20, choices=LevelChoices.choices, default=LevelChoices.INFO, verbose_name="等级")
    is_published = models.BooleanField(default=True, verbose_name="已发布")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "通知公告"
        verbose_name_plural = "通知公告"

    def __str__(self):
        return self.title


class SystemSetting(TimeStampedModel):
    key = models.CharField(max_length=80, unique=True, verbose_name="配置键")
    value = models.TextField(verbose_name="配置值")
    description = models.CharField(max_length=200, blank=True, verbose_name="说明")
    is_sensitive = models.BooleanField(default=False, verbose_name="敏感配置")

    class Meta:
        ordering = ["key"]
        verbose_name = "系统参数"
        verbose_name_plural = "系统参数"

    def __str__(self):
        return self.key


class EncryptedSecret(TimeStampedModel):
    namespace = models.CharField(max_length=120, verbose_name="命名空间")
    object_id = models.CharField(max_length=64, verbose_name="对象ID")
    field_name = models.CharField(max_length=64, verbose_name="字段名")
    ciphertext = models.TextField(verbose_name="密文")

    class Meta:
        ordering = ["namespace", "object_id", "field_name"]
        verbose_name = "加密密文"
        verbose_name_plural = "加密密文"
        constraints = [
            models.UniqueConstraint(
                fields=["namespace", "object_id", "field_name"],
                name="uniq_encrypted_secret_namespace_object_field",
            )
        ]
        indexes = [
            models.Index(fields=["namespace", "object_id"], name="idx_secret_namespace_obj"),
            models.Index(fields=["updated_at"], name="idx_secret_updated_at"),
        ]

    def __str__(self):
        return f"{self.namespace}:{self.object_id}:{self.field_name}"
