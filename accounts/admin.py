from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import Role, SessionRecord, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "full_name", "email", "status", "is_staff", "last_login")
    list_filter = ("status", "is_staff", "is_superuser")
    filter_horizontal = ("groups", "user_permissions", "roles")
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "企业信息",
            {
                "fields": (
                    "full_name",
                    "phone_number",
                    "status",
                    "password_changed_at",
                    "failed_login_attempts",
                    "locked_until",
                    "roles",
                )
            },
        ),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "data_scope", "updated_at")
    search_fields = ("name", "description")
    filter_horizontal = ("permissions",)


@admin.register(SessionRecord)
class SessionRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "ip_address", "login_at", "logout_at", "status")
    list_filter = ("status",)
    search_fields = ("user__username", "ip_address")

