from django.conf import settings
from django.db import models

from assets.models import AssetEnvironmentChoices
from core.models import ManagedModel


class PortMapping(models.Model):
    class ProtocolChoices(models.TextChoices):
        TCP = "TCP", "TCP"
        UDP = "UDP", "UDP"

    id = models.AutoField(primary_key=True, verbose_name="主键ID")
    interface = models.CharField(max_length=50, verbose_name="网络接口")
    protocol = models.CharField(
        max_length=20,
        choices=ProtocolChoices.choices,
        default=ProtocolChoices.TCP,
        verbose_name="协议",
    )
    public_ip = models.CharField(max_length=15, verbose_name="公网IP")
    public_port = models.CharField(max_length=20, verbose_name="公网端口")
    private_ip = models.CharField(max_length=15, verbose_name="内网IP")
    private_port = models.CharField(max_length=20, verbose_name="内网端口")
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name="更新时间")

    class Meta:
        managed = False
        db_table = "nat_mappings"
        ordering = ["interface", "public_ip", "public_port", "-updated_at"]
        verbose_name = "端口映射"
        verbose_name_plural = "端口映射"

    def __str__(self):
        return f"{self.public_ip}:{self.public_port} -> {self.private_ip}:{self.private_port}"


class DomainMapping(ManagedModel):
    class RecordTypeChoices(models.TextChoices):
        A = "A", "A"
        CNAME = "CNAME", "CNAME"

    domain = models.CharField(max_length=160, unique=True, verbose_name="域名")
    record_type = models.CharField(
        max_length=20,
        choices=RecordTypeChoices.choices,
        default=RecordTypeChoices.A,
        verbose_name="记录类型",
    )
    target = models.CharField(max_length=200, verbose_name="解析目标")
    environment = models.CharField(
        max_length=20,
        choices=AssetEnvironmentChoices.choices,
        default=AssetEnvironmentChoices.TEST,
        verbose_name="环境",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="domain_mappings",
        verbose_name="负责人",
    )
    description = models.CharField(max_length=255, blank=True, verbose_name="说明")

    class Meta:
        ordering = ["domain"]
        verbose_name = "域名映射"
        verbose_name_plural = "域名映射"

    def __str__(self):
        return self.domain


class DNSRecord(models.Model):
    id = models.AutoField(primary_key=True, verbose_name="主键 ID")
    platform = models.CharField(max_length=20, blank=True, null=True, verbose_name="DNS 平台")
    domain_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="主域名")
    sub_domain = models.CharField(max_length=255, blank=True, null=True, verbose_name="子域名")
    record_type = models.CharField(max_length=20, blank=True, null=True, verbose_name="记录类型")
    record_line = models.CharField(max_length=255, blank=True, null=True, verbose_name="解析线路")
    record_value = models.CharField(max_length=255, blank=True, null=True, verbose_name="记录值")
    ttl = models.IntegerField(blank=True, null=True, verbose_name="TTL")
    status = models.CharField(max_length=20, blank=True, null=True, verbose_name="状态")
    weight = models.IntegerField(blank=True, null=True, verbose_name="权重")
    mx_priority = models.IntegerField(blank=True, null=True, verbose_name="MX 优先级")
    comment = models.CharField(max_length=255, blank=True, null=True, verbose_name="备注")
    created_at = models.DateTimeField(blank=True, null=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(blank=True, null=True, verbose_name="更新时间")
    raw_id = models.CharField(max_length=64, blank=True, null=True, verbose_name="源平台记录 ID")
    last_sync_time = models.DateTimeField(blank=True, null=True, verbose_name="最后同步时间")

    class Meta:
        managed = False
        db_table = "dns_records_all"
        ordering = ["-updated_at", "-id"]
        verbose_name = "DNS 记录"
        verbose_name_plural = "DNS 记录"

    def __str__(self):
        return self.fqdn

    @property
    def fqdn(self):
        if self.sub_domain and self.sub_domain != "@":
            return f"{self.sub_domain}.{self.domain_name}"
        return self.domain_name or "-"

    @property
    def platform_label(self):
        value = (self.platform or "").strip()
        normalized = value.lower()
        if normalized == "dnsdjcn":
            return "数字引擎"
        if normalized == "alidns":
            return "阿里云"
        return value or "-"

    @property
    def status_label(self):
        value = (self.status or "").strip()
        normalized = value.lower()
        if normalized in {"enable", "enabled", "启用"}:
            return "启用"
        if normalized in {"disable", "disabled", "停用"}:
            return "停用"
        return value or "-"
