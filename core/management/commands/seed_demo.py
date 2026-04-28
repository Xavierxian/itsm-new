from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand

from accounts.models import Role, User


class Command(BaseCommand):
    help = "Create demo roles and an admin user for local development."

    def handle(self, *args, **options):
        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@example.com",
                "full_name": "平台管理员",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin_user.set_password("Admin@123456")
            admin_user.save()

        role, _ = Role.objects.get_or_create(
            name="运维管理员",
            defaults={"description": "默认示例角色", "data_scope": Role.DataScopeChoices.ALL},
        )
        role.permissions.set(Permission.objects.all())
        admin_user.roles.add(role)
        self.stdout.write(self.style.SUCCESS("已创建 admin 用户，初始密码为 Admin@123456"))
