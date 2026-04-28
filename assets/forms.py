from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from assets.models import Namespace, PhysicalHost, PurchaseDetail, QualificationManagement, VirtualMachine
from core.secret_store import MASKED_SECRET_PLACEHOLDER, has_instance_secret, set_instance_secret

KEEP_SECRET_SENTINEL = "__KEEP_SECRET__"


class SecretFieldFormMixin:
    secret_field_names = ()

    def _clean_secret_value(self, field_name):
        value = self.cleaned_data.get(field_name)
        if value in (None, "") and getattr(self.instance, "pk", None):
            if has_instance_secret(self.instance, field_name):
                return KEEP_SECRET_SENTINEL
            return getattr(self.instance, field_name, "")
        return value

    def _persist_secret_fields(self, instance):
        for field_name in self.secret_field_names:
            value = self.cleaned_data.get(field_name)
            if value == KEEP_SECRET_SENTINEL:
                setattr(instance, field_name, MASKED_SECRET_PLACEHOLDER)
                continue
            if value in (None, ""):
                if getattr(instance, "pk", None) and has_instance_secret(instance, field_name):
                    setattr(instance, field_name, MASKED_SECRET_PLACEHOLDER)
                continue
            setattr(instance, field_name, MASKED_SECRET_PLACEHOLDER)

    def _save_secret_fields(self, instance):
        for field_name in self.secret_field_names:
            value = self.cleaned_data.get(field_name)
            if value in (None, "", KEEP_SECRET_SENTINEL):
                continue
            set_instance_secret(instance, field_name, value)


class VirtualMachineForm(SecretFieldFormMixin, forms.ModelForm):
    secret_field_names = ("boot_password",)
    OS_CHOICES = (
        ("CentOS", "CentOS"),
        ("Windows", "Windows"),
        ("Ubuntu", "Ubuntu"),
        ("XenServer", "XenServer"),
    )
    LOGIN_CHOICES = (
        ("root", "root"),
        ("administrator", "administrator"),
    )
    ENV_CHOICES = (
        ("正式", "正式"),
        ("测试", "测试"),
    )
    IN_USE_CHOICES = (
        ("在用", "在用"),
        ("停用", "停用"),
    )

    os_name = forms.ChoiceField(choices=OS_CHOICES, label="操作系统", required=False)
    login_name = forms.ChoiceField(choices=LOGIN_CHOICES, label="登录名", required=False)
    environment = forms.ChoiceField(choices=ENV_CHOICES, label="环境", required=False)
    in_use = forms.ChoiceField(choices=IN_USE_CHOICES, label="是否在用", required=False)

    class Meta:
        model = VirtualMachine
        fields = [
            "host_ip",
            "vm_ip",
            "os_name",
            "os_version",
            "login_name",
            "remote_port",
            "boot_password",
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
        ]
        widgets = {
            "boot_password": forms.PasswordInput(render_value=False),
            "purpose": forms.Textarea(attrs={"rows": 2}),
            "open_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("open_date", "end_date"):
            self.fields[field_name].input_formats = ["%Y-%m-%d"]
            value = getattr(self.instance, field_name, None)
            if value:
                self.initial[field_name] = value.strftime("%Y-%m-%d")

        dynamic_choice_fields = ("os_name", "login_name", "environment", "in_use")
        for field_name in dynamic_choice_fields:
            current = (getattr(self.instance, field_name, "") or "").strip()
            field = self.fields[field_name]
            choices = list(field.choices)
            if current and current not in [value for value, _ in choices]:
                choices.insert(0, (current, f"{current}（历史值）"))
            field.choices = choices

        for field_name in ("environment", "open_date", "end_date"):
            widget = self.fields[field_name].widget
            existing_class = widget.attrs.get("class", "")
            widget.attrs["class"] = (existing_class + " vm-compact-control").strip()

        purpose_widget = self.fields["purpose"].widget
        purpose_existing_class = purpose_widget.attrs.get("class", "")
        purpose_widget.attrs["class"] = (purpose_existing_class + " vm-purpose-compact").strip()

    def clean_open_date(self):
        value = self.cleaned_data.get("open_date")
        if value in (None, "") and getattr(self.instance, "pk", None):
            return self.instance.open_date
        return value

    def clean_end_date(self):
        value = self.cleaned_data.get("end_date")
        if value in (None, "") and getattr(self.instance, "pk", None):
            return self.instance.end_date
        return value

    def clean_boot_password(self):
        return self._clean_secret_value("boot_password")

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._persist_secret_fields(instance)
        if commit:
            instance.save()
            self._save_secret_fields(instance)
        return instance


class PhysicalHostForm(SecretFieldFormMixin, forms.ModelForm):
    secret_field_names = ("login_password",)
    class Meta:
        model = PhysicalHost
        fields = [
            "server_ip",
            "model_name",
            "purchase_channel",
            "purchase_date",
            "port",
            "login_password",
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
        ]
        widgets = {
            "login_password": forms.PasswordInput(render_value=False),
        }

    def clean_login_password(self):
        return self._clean_secret_value("login_password")

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._persist_secret_fields(instance)
        if commit:
            instance.save()
            self._save_secret_fields(instance)
        return instance


class NamespaceForm(forms.ModelForm):
    class Meta:
        model = Namespace
        fields = [
            "namespace_name",
            "space_owner",
            "request_department",
            "space_contact",
            "service_engineer",
            "open_date",
            "expiry_date",
            "purpose",
            "disabled",
        ]
        widgets = {
            "open_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "expiry_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("open_date", "expiry_date"):
            self.fields[field_name].input_formats = ["%Y-%m-%d"]
            value = getattr(self.instance, field_name, None)
            if value:
                self.initial[field_name] = value.strftime("%Y-%m-%d")


class QualificationManagementForm(SecretFieldFormMixin, forms.ModelForm):
    secret_field_names = ("password",)
    STATUS_CHOICES = (
        ("", "请选择状态"),
        ("启用", "启用"),
        ("停用", "停用"),
    )
    status = forms.ChoiceField(choices=STATUS_CHOICES, label="状态", required=False)

    class Meta:
        model = QualificationManagement
        fields = [
            "qualification_category",
            "belong_entity",
            "belong_department",
            "qualification_name",
            "manager",
            "usage",
            "cost",
            "account",
            "password",
            "status",
            "expire_date",
            "supplier_name",
            "remark",
        ]
        widgets = {
            "password": forms.PasswordInput(render_value=False),
            "usage": forms.Textarea(attrs={"rows": 2}),
            "remark": forms.Textarea(attrs={"rows": 2}),
            "expire_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expire_date"].input_formats = ["%Y-%m-%d"]
        if self.instance and self.instance.expire_date:
            self.initial["expire_date"] = self.instance.expire_date.strftime("%Y-%m-%d")

        current_status = (getattr(self.instance, "status", "") or "").strip()
        if current_status and current_status not in [value for value, _ in self.STATUS_CHOICES]:
            choices = list(self.fields["status"].choices)
            choices.insert(1, (current_status, f"{current_status}（历史值）"))
            self.fields["status"].choices = choices

    def clean_password(self):
        return self._clean_secret_value("password")

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._persist_secret_fields(instance)
        if commit:
            instance.save()
            self._save_secret_fields(instance)
        return instance


class PurchaseDetailForm(forms.ModelForm):
    class Meta:
        model = PurchaseDetail
        fields = ["create_time", "cost_amount", "expire_date", "remark"]
        widgets = {
            "create_time": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "expire_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "remark": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["create_time"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["expire_date"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["create_time"].required = False
        self.fields["cost_amount"].required = False
        self.fields["expire_date"].required = False

        if self.instance and self.instance.create_time:
            self.initial["create_time"] = timezone.localtime(self.instance.create_time).strftime("%Y-%m-%dT%H:%M")
        else:
            self.fields["cost_amount"].initial = ""

        if self.instance and self.instance.expire_date:
            self.initial["expire_date"] = timezone.localtime(self.instance.expire_date).strftime("%Y-%m-%dT%H:%M")

    def _has_any_user_input(self):
        for field_name in ("create_time", "cost_amount", "expire_date", "remark"):
            raw_value = self.data.get(self.add_prefix(field_name), "")
            if str(raw_value).strip():
                return True
        return False

    def clean_create_time(self):
        value = self.cleaned_data.get("create_time")
        if value:
            return value
        if self.is_bound and self._has_any_user_input():
            return timezone.now()
        return None

    def clean_cost_amount(self):
        value = self.cleaned_data.get("cost_amount")
        if value in (None, "") and self.is_bound and self._has_any_user_input():
            return 0
        return value


PurchaseDetailFormSet = inlineformset_factory(
    QualificationManagement,
    PurchaseDetail,
    form=PurchaseDetailForm,
    extra=0,
    can_delete=True,
)


class PurchaseDetailManageForm(forms.ModelForm):
    class Meta:
        model = PurchaseDetail
        fields = ["create_time", "cost_amount", "expire_date", "remark"]
        widgets = {
            "create_time": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "expire_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "remark": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["create_time"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["expire_date"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["create_time"].required = False
        self.fields["cost_amount"].required = False
        self.fields["expire_date"].required = False

        if self.instance and self.instance.create_time:
            self.initial["create_time"] = timezone.localtime(self.instance.create_time).strftime("%Y-%m-%dT%H:%M")
        if self.instance and self.instance.expire_date:
            self.initial["expire_date"] = timezone.localtime(self.instance.expire_date).strftime("%Y-%m-%dT%H:%M")

    def clean_create_time(self):
        return self.cleaned_data.get("create_time") or timezone.now()

    def clean_cost_amount(self):
        value = self.cleaned_data.get("cost_amount")
        return 0 if value in (None, "") else value
