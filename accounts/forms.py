from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import Permission

from accounts.models import Role

User = get_user_model()


class LoginForm(forms.Form):
    username = forms.CharField(label="账号", max_length=150)
    password = forms.CharField(label="密码", widget=forms.PasswordInput(render_value=False))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "autocomplete": "username",
                "placeholder": "输入账号名",
                "autofocus": "autofocus",
                "spellcheck": "false",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "autocomplete": "current-password",
                "placeholder": "输入登录密码",
            }
        )


class UserForm(forms.ModelForm):
    password = forms.CharField(label="密码", required=False, widget=forms.PasswordInput(render_value=False))

    class Meta:
        model = User
        fields = [
            "username",
            "full_name",
            "email",
            "phone_number",
            "status",
            "is_staff",
            "roles",
            "password",
        ]
        widgets = {
            "roles": forms.SelectMultiple(
                attrs={
                    "size": 6,
                    "data-enhanced-multiselect": "1",
                }
            ),
        }

    def save(self, commit=True):
        original_password = ""
        if self.instance.pk:
            original_password = (
                User.objects.filter(pk=self.instance.pk).values_list("password", flat=True).first() or ""
            )
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        elif user.pk:
            user.password = original_password
        else:
            user.set_unusable_password()
        if commit:
            user.save()
            self.save_m2m()
        return user


class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.select_related("content_type").order_by("content_type__app_label", "codename"),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "size": 12,
                "data-enhanced-permission-select": "1",
            }
        ),
        label="权限",
    )

    class Meta:
        model = Role
        fields = ["name", "description", "data_scope", "permissions"]


class ProfilePasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "当前密码"
        self.fields["new_password1"].label = "新密码"
        self.fields["new_password2"].label = "确认新密码"

        self.error_messages["password_incorrect"] = "当前密码不正确。"
        self.error_messages["password_mismatch"] = "两次输入的新密码不一致。"

        for name, field in self.fields.items():
            field.widget.attrs.update(
                {
                    "autocomplete": "current-password" if name == "old_password" else "new-password",
                    "placeholder": {
                        "old_password": "输入当前密码",
                        "new_password1": "输入新密码",
                        "new_password2": "再次输入新密码",
                    }.get(name, ""),
                }
            )
