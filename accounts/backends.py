from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Permission


class RolePermissionBackend(ModelBackend):
    def get_all_permissions(self, user_obj, obj=None):
        permissions = super().get_all_permissions(user_obj, obj)
        if not user_obj.is_authenticated or obj is not None:
            return permissions
        role_permissions = Permission.objects.filter(itsm_roles__users=user_obj).values_list(
            "content_type__app_label", "codename"
        )
        permissions.update({f"{app_label}.{codename}" for app_label, codename in role_permissions})
        return permissions

