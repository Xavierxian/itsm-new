from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Permission
from django.db import models
from django.utils import timezone


class Role(models.Model):
    class DataScopeChoices(models.TextChoices):
        ALL = "all", "全部数据"
        TEAM = "team", "本组数据"
        SELF = "self", "本人数据"

    name = models.CharField(max_length=80, unique=True, verbose_name="角色名称")
    description = models.CharField(max_length=200, blank=True, verbose_name="角色说明")
    data_scope = models.CharField(max_length=20, choices=DataScopeChoices.choices, default=DataScopeChoices.SELF, verbose_name="数据范围")
    permissions = models.ManyToManyField(Permission, blank=True, related_name="itsm_roles", verbose_name="权限")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "角色"
        verbose_name_plural = "角色"

    def __str__(self):
        return self.name


class User(AbstractUser):
    class StatusChoices(models.TextChoices):
        ACTIVE = "active", "启用"
        DISABLED = "disabled", "禁用"
        LOCKED = "locked", "锁定"

    full_name = models.CharField(max_length=120, blank=True, verbose_name="姓名")
    phone_number = models.CharField(max_length=30, blank=True, verbose_name="手机号")
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.ACTIVE, verbose_name="状态")
    password_changed_at = models.DateTimeField(blank=True, null=True, verbose_name="密码更新时间")
    failed_login_attempts = models.PositiveIntegerField(default=0, verbose_name="失败次数")
    locked_until = models.DateTimeField(blank=True, null=True, verbose_name="锁定至")
    roles = models.ManyToManyField(Role, blank=True, related_name="users", verbose_name="角色")

    class Meta:
        ordering = ["username"]
        verbose_name = "用户"
        verbose_name_plural = "用户"

    def save(self, *args, **kwargs):
        if not self.full_name:
            self.full_name = self.username

        previous_status = None
        if self.pk:
            previous_status = (
                self.__class__.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            )

        # Admin manual re-activation should immediately unlock the account.
        if previous_status == self.StatusChoices.LOCKED and self.status == self.StatusChoices.ACTIVE:
            self.failed_login_attempts = 0
            self.locked_until = None
        super().save(*args, **kwargs)

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def reset_login_failures(self):
        self.failed_login_attempts = 0
        self.locked_until = None
        if self.status == self.StatusChoices.LOCKED:
            self.status = self.StatusChoices.ACTIVE

    def register_login_failure(self, lock_minutes):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= settings.LOGIN_FAILURE_LIMIT:
            self.locked_until = timezone.now() + timedelta(minutes=lock_minutes)
            self.status = self.StatusChoices.LOCKED


class SessionRecord(models.Model):
    class SessionStatusChoices(models.TextChoices):
        ACTIVE = "active", "在线"
        LOGGED_OUT = "logged_out", "已退出"
        EXPIRED = "expired", "已过期"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions", verbose_name="用户")
    session_key = models.CharField(max_length=40, blank=True, verbose_name="会话键")
    login_at = models.DateTimeField(auto_now_add=True, verbose_name="登录时间")
    logout_at = models.DateTimeField(blank=True, null=True, verbose_name="退出时间")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="IP 地址")
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="客户端")
    status = models.CharField(max_length=20, choices=SessionStatusChoices.choices, default=SessionStatusChoices.ACTIVE, verbose_name="状态")

    class Meta:
        ordering = ["-login_at"]
        verbose_name = "会话记录"
        verbose_name_plural = "会话记录"

    def __str__(self):
        return f"{self.user} - {self.login_at:%Y-%m-%d %H:%M}"
