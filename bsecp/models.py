from django.db import models


class Module(models.Model):
    id = models.AutoField(primary_key=True, db_column="MD_ID", verbose_name="MD_ID")
    md_code = models.CharField(max_length=50, db_column="MD_CODE", verbose_name="MD_CODE")
    md_name = models.CharField(max_length=200, db_column="MD_NAME", verbose_name="MD_NAME")
    md_productid = models.IntegerField(db_column="MD_PRODUCTID", verbose_name="MD_PRODUCTID")
    md_productcode = models.CharField(max_length=50, blank=True, null=True, db_column="MD_PRODUCTCODE", verbose_name="MD_PRODUCTCODE")
    md_ispoint = models.IntegerField(db_column="MD_ISPOINT", verbose_name="MD_ISPOINT")
    md_price = models.DecimalField(max_digits=18, decimal_places=2, db_column="MD_PRICE", verbose_name="MD_PRICE")
    md_state = models.IntegerField(blank=True, null=True, db_column="MD_STATE", verbose_name="MD_STATE")
    md_remark = models.CharField(max_length=100, blank=True, null=True, db_column="MD_REMARK", verbose_name="MD_REMARK")
    md_forbit_date = models.DateTimeField(blank=True, null=True, db_column="MD_FORBIT_DATE", verbose_name="MD_FORBIT_DATE")
    md_forbit_id = models.IntegerField(blank=True, null=True, db_column="MD_FORBIT_ID", verbose_name="MD_FORBIT_ID")
    md_forbit_user = models.CharField(max_length=50, blank=True, null=True, db_column="MD_FORBIT_USER", verbose_name="MD_FORBIT_USER")
    md_create_date = models.DateTimeField(blank=True, null=True, db_column="MD_CREATE_DATE", verbose_name="MD_CREATE_DATE")
    md_create_id = models.IntegerField(blank=True, null=True, db_column="MD_CREATE_ID", verbose_name="MD_CREATE_ID")
    md_create_user = models.CharField(max_length=50, blank=True, null=True, db_column="MD_CREATE_USER", verbose_name="MD_CREATE_USER")
    md_modify_date = models.DateTimeField(blank=True, null=True, db_column="MD_MODIFY_DATE", verbose_name="MD_MODIFY_DATE")
    md_modify_id = models.IntegerField(blank=True, null=True, db_column="MD_MODIFY_ID", verbose_name="MD_MODIFY_ID")
    md_modify_user = models.CharField(max_length=50, blank=True, null=True, db_column="MD_MODIFY_USER", verbose_name="MD_MODIFY_USER")

    class Meta:
        db_table = "cljc_module"
        ordering = ["-id"]
        verbose_name = "Module"
        verbose_name_plural = "Module"

    def __str__(self):
        return self.md_name

    @property
    def md_create_date_display(self):
        annotated_value = self.__dict__.get("md_create_date_text")
        if annotated_value not in (None, ""):
            text = str(annotated_value).strip()
            if not text:
                return "-"
            # Keep list-page formatting stable for either datetime or raw text.
            return text.replace("-", "/")[:16]

        if "md_create_date" not in self.__dict__:
            return "-"

        value = self.__dict__.get("md_create_date")
        if value is None:
            return "-"
        if hasattr(value, "strftime"):
            return value.strftime("%Y/%m/%d %H:%M")
        return str(value)


class AuthorizationScope(models.Model):
    class ScopeTypeChoices(models.TextChoices):
        GLOBAL = "global", "全局"
        ENVIRONMENT = "environment", "环境"
        RESOURCE = "resource", "资源"

    name = models.CharField(max_length=80, unique=True, verbose_name="范围名称")
    scope_type = models.CharField(max_length=20, choices=ScopeTypeChoices.choices, default=ScopeTypeChoices.RESOURCE, verbose_name="范围类型")
    description = models.CharField(max_length=255, blank=True, verbose_name="说明")

    class Meta:
        ordering = ["name"]
        verbose_name = "授权范围"
        verbose_name_plural = "授权范围"

    def __str__(self):
        return self.name


class AuthorizationRecord(models.Model):
    FId = models.AutoField(primary_key=True, db_column="FId", verbose_name="Primary ID")
    OD_SERIAL_NUMBER = models.CharField(max_length=255, blank=True, null=True, db_column="OD_SERIAL_NUMBER", verbose_name="Order Serial Number")
    OD_CONTRACT_NUMBER = models.CharField(max_length=255, blank=True, null=True, db_column="OD_CONTRACT_NUMBER", verbose_name="Contract Number")
    OD_BMPID = models.CharField(max_length=255, blank=True, null=True, db_column="OD_BMPID", verbose_name="Business Primary ID")
    AutoAuthFlag = models.CharField(max_length=255, blank=True, null=True, db_column="AutoAuthFlag", verbose_name="Auto Authorization Flag")
    Remark = models.TextField(blank=True, null=True, db_column="Remark", verbose_name="Remark")
    CreateTime = models.DateTimeField(blank=True, null=True, db_column="CreateTime", verbose_name="Create Time")
    AutoAuthHandleTime = models.DateTimeField(blank=True, null=True, db_column="AutoAuthHandleTime", verbose_name="Auto Auth Handle Time")
    AutoAuthHandleResult = models.CharField(max_length=255, blank=True, null=True, db_column="AutoAuthHandleResult", verbose_name="Auto Auth Handle Result")
    AutoAuthHandleResultDesc = models.TextField(blank=True, null=True, db_column="AutoAuthHandleResultDesc", verbose_name="Auto Auth Handle Result Description")

    class Meta:
        db_table = "OrderAutoAuthorizationQueue"
        managed = False
        ordering = ["-FId"]
        verbose_name = "Order Auto Authorization Queue"
        verbose_name_plural = "Order Auto Authorization Queue"

    def __str__(self):
        return self.OD_SERIAL_NUMBER or self.OD_CONTRACT_NUMBER or str(self.FId)
