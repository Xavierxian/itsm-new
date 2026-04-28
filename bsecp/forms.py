from django import forms

from bsecp.models import AuthorizationRecord, Module


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = [
            "md_code",
            "md_name",
            "md_productid",
            "md_productcode",
            "md_ispoint",
            "md_price",
            "md_state",
            "md_remark",
            "md_forbit_date",
            "md_forbit_id",
            "md_forbit_user",
            "md_create_date",
            "md_create_id",
            "md_create_user",
            "md_modify_date",
            "md_modify_id",
            "md_modify_user",
        ]
        widgets = {
            "md_forbit_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "md_create_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "md_modify_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        datetime_fields = ("md_forbit_date", "md_create_date", "md_modify_date")
        for field_name in datetime_fields:
            self.fields[field_name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
            value = getattr(self.instance, field_name, None)
            if value and hasattr(value, "strftime"):
                self.initial[field_name] = value.strftime("%Y-%m-%dT%H:%M")


class AuthorizationRecordForm(forms.ModelForm):
    class Meta:
        model = AuthorizationRecord
        fields = [
            "OD_SERIAL_NUMBER",
            "OD_CONTRACT_NUMBER",
            "OD_BMPID",
            "AutoAuthFlag",
            "Remark",
            "CreateTime",
            "AutoAuthHandleTime",
            "AutoAuthHandleResult",
            "AutoAuthHandleResultDesc",
        ]
        widgets = {
            "CreateTime": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "AutoAuthHandleTime": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
