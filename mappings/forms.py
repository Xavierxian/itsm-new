from django import forms

from mappings.models import DomainMapping, PortMapping


class PortMappingForm(forms.ModelForm):
    INTERFACE_CHOICES = (
        ("GigabitEthernet0/1", "GigabitEthernet0/1"),
        ("GigabitEthernet0/2", "GigabitEthernet0/2"),
        ("GigabitEthernet0/3", "GigabitEthernet0/3"),
    )

    interface = forms.ChoiceField(choices=INTERFACE_CHOICES, label="网络接口")

    class Meta:
        model = PortMapping
        fields = [
            "interface",
            "protocol",
            "public_ip",
            "public_port",
            "private_ip",
            "private_port",
        ]

    def clean_public_port(self):
        value = str(self.cleaned_data.get("public_port", "")).strip()
        if not value:
            raise forms.ValidationError("公网端口不能为空。")
        return value

    def clean_private_port(self):
        value = str(self.cleaned_data.get("private_port", "")).strip()
        if not value:
            raise forms.ValidationError("内网端口不能为空。")
        return value


class DomainMappingForm(forms.ModelForm):
    class Meta:
        model = DomainMapping
        fields = ["domain", "record_type", "target", "environment", "owner", "status", "description"]
