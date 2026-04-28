from django.db import models
from django.utils import timezone

from core.secret_store import get_instance_secret


class AssetEnvironmentChoices(models.TextChoices):
    PROD = "prod", "生产"
    STAGING = "staging", "预发"
    TEST = "test", "测试"
    DEV = "dev", "开发"


class VirtualMachine(models.Model):
    id = models.AutoField(primary_key=True, verbose_name="ID")
    host_ip = models.CharField(max_length=15, blank=True, null=True, db_column="主机IP", verbose_name="主机IP")
    vm_ip = models.CharField(max_length=15, blank=True, null=True, db_column="虚拟机IP", verbose_name="虚拟机IP")
    os_name = models.CharField(max_length=50, blank=True, null=True, db_column="操作系统", verbose_name="操作系统")
    os_version = models.CharField(max_length=10, blank=True, null=True, db_column="系统版本", verbose_name="系统版本")
    login_name = models.CharField(max_length=50, blank=True, null=True, db_column="登录名", verbose_name="登录名")
    remote_port = models.IntegerField(blank=True, null=True, db_column="远程端口", verbose_name="远程端口")
    boot_password = models.CharField(max_length=255, blank=True, null=True, db_column="开机密码", verbose_name="开机密码")
    cpu = models.IntegerField(blank=True, null=True, db_column="CPU", verbose_name="CPU")
    memory = models.IntegerField(blank=True, null=True, db_column="内存", verbose_name="内存")
    disk = models.IntegerField(blank=True, null=True, db_column="硬盘", verbose_name="硬盘")
    applicant = models.CharField(max_length=50, blank=True, null=True, db_column="申请人", verbose_name="申请人")
    department = models.CharField(max_length=50, blank=True, null=True, db_column="部门", verbose_name="部门")
    purpose = models.CharField(max_length=255, blank=True, null=True, db_column="用途", verbose_name="用途")
    environment = models.CharField(max_length=50, blank=True, null=True, db_column="环境", verbose_name="环境")
    open_date = models.DateField(blank=True, null=True, db_column="开通日期", verbose_name="开通日期")
    in_use = models.CharField(max_length=5, blank=True, null=True, db_column="是否在用", verbose_name="是否在用")
    end_date = models.DateField(blank=True, null=True, db_column="结束日期", verbose_name="结束日期")

    class Meta:
        managed = False
        db_table = "assets"
        ordering = ["-id"]
        verbose_name = "虚拟机资产"
        verbose_name_plural = "虚拟机资产"

    def __str__(self):
        return self.vm_ip or self.host_ip or f"资产-{self.pk}"

    @property
    def os_summary(self):
        os_name = (self.os_name or "").strip()
        os_version = (self.os_version or "").strip()
        if os_name and os_version:
            return f"{os_name} {os_version}"
        return os_name or os_version or "-"

    @property
    def spec_summary(self):
        cpu = "-" if self.cpu is None else str(self.cpu)
        memory = "-" if self.memory is None else str(self.memory)
        disk = "-" if self.disk is None else str(self.disk)
        return f"CPU {cpu} / 内存 {memory} / 硬盘 {disk}"

    @property
    def spec_compact(self):
        cpu = "-" if self.cpu is None else str(self.cpu)
        memory = "-" if self.memory is None else str(self.memory)
        disk = "-" if self.disk is None else str(self.disk)
        return f"{cpu}核/{memory}GB/{disk}GB"

    @property
    def owner_summary(self):
        applicant = (self.applicant or "").strip()
        department = (self.department or "").strip()
        if applicant and department:
            return f"{applicant} / {department}"
        return applicant or department or "-"

    @property
    def environment_label(self):
        value = (self.environment or "").strip()
        normalized = value.lower()
        if normalized in {"正式", "prod", "production"}:
            return "正式"
        if normalized in {"测试", "test"}:
            return "测试"
        return value or "-"

    @property
    def period_summary(self):
        open_date = self.open_date.strftime("%Y-%m-%d") if self.open_date else "-"
        end_date = self.end_date.strftime("%Y-%m-%d") if self.end_date else "-"
        return f"{open_date} ~ {end_date}"

    @property
    def in_use_label(self):
        value = (self.in_use or "").strip().lower()
        if value in {"是", "y", "yes", "1", "true", "在用", "启用", "enabled"}:
            return "在用"
        if value in {"否", "n", "no", "0", "false", "停用", "禁用", "disabled"}:
            return "停用"
        return (self.in_use or "-").strip() or "-"

    @property
    def in_use_tone(self):
        if self.in_use_label == "在用":
            return "success"
        if self.in_use_label == "停用":
            return "danger"
        return "neutral"

    @property
    def boot_password_plaintext(self):
        return get_instance_secret(self, "boot_password")


class PhysicalHost(models.Model):
    id = models.AutoField(primary_key=True, verbose_name="ID")
    server_ip = models.CharField(max_length=50, blank=True, null=True, db_column="服务器IP", verbose_name="服务器IP")
    model_name = models.CharField(max_length=50, blank=True, null=True, db_column="型号", verbose_name="型号")
    purchase_channel = models.CharField(max_length=50, blank=True, null=True, db_column="购买途径", verbose_name="购买途径")
    purchase_date = models.CharField(max_length=50, blank=True, null=True, db_column="购买日期", verbose_name="购买日期")
    port = models.CharField(max_length=50, blank=True, null=True, db_column="端口", verbose_name="端口")
    login_password = models.CharField(max_length=50, blank=True, null=True, db_column="登录密码", verbose_name="登录密码")
    memory = models.CharField(max_length=50, blank=True, null=True, db_column="内存", verbose_name="内存")
    disk = models.CharField(max_length=50, blank=True, null=True, db_column="磁盘", verbose_name="磁盘")
    disk_type = models.CharField(max_length=50, blank=True, null=True, db_column="硬盘类型", verbose_name="硬盘类型")
    memory_used = models.CharField(max_length=50, blank=True, null=True, db_column="内存已使用", verbose_name="内存已使用")
    disk_used = models.CharField(max_length=50, blank=True, null=True, db_column="磁盘已使用", verbose_name="磁盘已使用")
    memory_remaining = models.CharField(max_length=50, blank=True, null=True, db_column="内存剩余", verbose_name="内存剩余")
    disk_remaining = models.CharField(max_length=50, blank=True, null=True, db_column="磁盘剩余", verbose_name="磁盘剩余")
    remaining_capacity = models.CharField(max_length=50, blank=True, null=True, db_column="剩余可开", verbose_name="剩余可开")
    department = models.CharField(max_length=50, blank=True, null=True, db_column="部门", verbose_name="部门")
    purpose = models.CharField(max_length=50, blank=True, null=True, db_column="用途", verbose_name="用途")

    class Meta:
        db_table = "xenserver"
        ordering = ["-id"]
        verbose_name = "物理机"
        verbose_name_plural = "物理机"

    def __str__(self):
        return self.server_ip or f"物理机-{self.pk}"

    @property
    def login_password_plaintext(self):
        return get_instance_secret(self, "login_password")


class Namespace(models.Model):
    id = models.AutoField(primary_key=True, verbose_name="ID")
    namespace_name = models.CharField(max_length=50, blank=True, null=True, db_column="命名空间", verbose_name="命名空间")
    space_owner = models.CharField(max_length=50, blank=True, null=True, db_column="空间归属", verbose_name="空间归属")
    request_department = models.CharField(max_length=50, blank=True, null=True, db_column="申请部门", verbose_name="申请部门")
    space_contact = models.CharField(max_length=50, blank=True, null=True, db_column="空间对接人", verbose_name="空间对接人")
    service_engineer = models.CharField(max_length=50, blank=True, null=True, db_column="服务工程师", verbose_name="服务工程师")
    open_date = models.DateField(blank=True, null=True, db_column="开通日期", verbose_name="开通日期")
    expiry_date = models.DateField(blank=True, null=True, db_column="到期日期", verbose_name="到期日期")
    purpose = models.CharField(max_length=50, blank=True, null=True, db_column="用途", verbose_name="用途")
    disabled = models.CharField(max_length=50, blank=True, null=True, db_column="是否停用", verbose_name="是否停用")

    class Meta:
        db_table = "bseip"
        ordering = ["-id"]
        verbose_name = "NameSpace"
        verbose_name_plural = "NameSpace"

    def __str__(self):
        return self.namespace_name or f"NameSpace-{self.pk}"

    @property
    def disabled_label(self):
        value = (self.disabled or "").strip().lower()
        if value in {"是", "y", "yes", "1", "true", "停用", "禁用", "disabled"}:
            return "停用"
        if value in {"否", "n", "no", "0", "false", "启用", "正常", "enabled"}:
            return "启用"
        return (self.disabled or "-").strip() or "-"


class QualificationManagement(models.Model):
    id = models.AutoField(primary_key=True, verbose_name="ID")
    qualification_category = models.CharField(max_length=100, blank=True, null=True, verbose_name="资质类别")
    belong_entity = models.CharField(max_length=100, blank=True, null=True, verbose_name="归属主体")
    belong_department = models.CharField(max_length=100, blank=True, null=True, verbose_name="归属部门")
    qualification_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="资质名称")
    manager = models.CharField(max_length=100, blank=True, null=True, verbose_name="管理员")
    usage = models.CharField(max_length=100, blank=True, null=True, verbose_name="用途")
    cost = models.CharField(max_length=100, blank=True, null=True, verbose_name="费用")
    account = models.CharField(max_length=100, blank=True, null=True, verbose_name="账号")
    password = models.CharField(max_length=100, blank=True, null=True, verbose_name="密码（加密存储）")
    status = models.CharField(max_length=100, blank=True, null=True, verbose_name="状态")
    expire_date = models.DateField(blank=True, null=True, verbose_name="到期日")
    remark = models.CharField(max_length=200, blank=True, null=True, verbose_name="备注说明")
    supplier_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="供应商")
    last_update_time = models.DateTimeField(blank=True, null=True, verbose_name="最新修改日期")
    create_time = models.DateTimeField(blank=True, null=True, verbose_name="创建时间")

    class Meta:
        managed = False
        db_table = "qualification_management"
        ordering = ["-id"]
        verbose_name = "资质管理"
        verbose_name_plural = "资质管理"

    def __str__(self):
        return self.qualification_name or f"资质-{self.pk}"

    @property
    def status_label(self):
        return (self.status or "-").strip() or "-"

    @property
    def password_plaintext(self):
        return get_instance_secret(self, "password")


class PurchaseDetail(models.Model):
    id = models.AutoField(primary_key=True, verbose_name="ID")
    parent = models.ForeignKey(
        QualificationManagement,
        on_delete=models.CASCADE,
        related_name="purchase_details",
        db_column="parent_id",
        db_constraint=False,
        verbose_name="资质",
    )
    create_time = models.DateTimeField(default=timezone.now, verbose_name="购买记录创建时间")
    cost_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="成本金额")
    expire_date = models.DateTimeField(blank=True, null=True, verbose_name="到期日期")
    remark = models.CharField(max_length=200, blank=True, null=True, verbose_name="补充说明/备注")

    class Meta:
        managed = False
        db_table = "purchase_detail"
        ordering = ["-id"]
        verbose_name = "资质采购明细"
        verbose_name_plural = "资质采购明细"

    def __str__(self):
        return f"明细-{self.pk}"


