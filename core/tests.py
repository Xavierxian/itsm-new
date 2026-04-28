from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


class DashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dashboard-user",
            password="SecurePass@123",
            status="active",
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_renders_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "系统概览")


class PermissionDeniedPageTests(TestCase):
    @override_settings(DEBUG=False)
    def test_permission_denied_uses_custom_403_page(self):
        user = get_user_model().objects.create_user(
            username="no-perm-user",
            password="SecurePass@123",
            status="active",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:user-list"))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "你已登录，但没有访问这个页面的权限", status_code=403)
        self.assertContains(response, "Access Blocked", status_code=403)
