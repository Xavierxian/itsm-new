from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.forms import UserForm
from accounts.security import ip_rate_limit_key, ip_user_rate_limit_key, register_login_failure, user_failure_key
from logs.models import LoginLog


@override_settings(
    LOGIN_FAILURE_LIMIT=5,
    LOGIN_LOCK_MINUTES=15,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS=600,
    LOGIN_RATE_LIMIT_PER_IP=60,
    LOGIN_RATE_LIMIT_PER_IP_USER=10,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "accounts-tests-cache",
        }
    },
)
class LoginViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="tester",
            password="SecurePass@123",
            status="active",
            is_staff=True,
            is_active=True,
        )

    def test_login_page_has_security_headers(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_failed_login_creates_log(self):
        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "tester", "password": "bad-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(LoginLog.objects.filter(username="tester", success=False).exists())

    def test_failed_login_shows_remaining_attempts_hint(self):
        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "tester", "password": "bad-password"},
        )
        self.assertContains(response, "剩余 4 次")

    def test_repeated_failures_lock_user(self):
        for _ in range(5):
            self.client.post(
                reverse("accounts:login"),
                data={"username": "tester", "password": "bad-password"},
            )

        self.user.refresh_from_db()
        self.assertEqual(self.user.status, "locked")
        self.assertGreater(self.user.failed_login_attempts, 0)
        self.assertIsNotNone(self.user.locked_until)

    def test_locked_user_gets_429(self):
        self.user.failed_login_attempts = 5
        self.user.locked_until = timezone.now() + timedelta(minutes=15)
        self.user.status = "locked"
        self.user.save(update_fields=["failed_login_attempts", "locked_until", "status"])
        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "tester", "password": "SecurePass@123"},
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "账号已锁定", status_code=429)

    def test_rate_limited_user_gets_429(self):
        for _ in range(11):
            self.client.post(
                reverse("accounts:login"),
                data={"username": "tester", "password": "bad-password"},
            )
        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "tester", "password": "bad-password"},
        )
        self.assertEqual(response.status_code, 429)

    def test_reactivate_locked_user_can_login_immediately(self):
        self.user.failed_login_attempts = 5
        self.user.locked_until = timezone.now() + timedelta(minutes=15)
        self.user.status = "locked"
        self.user.save(update_fields=["failed_login_attempts", "locked_until", "status"])

        # Simulate admin operation: status changed from locked to active.
        self.user.status = "active"
        self.user.save(update_fields=["status", "failed_login_attempts", "locked_until"])

        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "tester", "password": "SecurePass@123"},
        )
        self.assertEqual(response.status_code, 302)


class UserFormTests(TestCase):
    def test_update_with_blank_password_preserves_existing_password(self):
        user = get_user_model().objects.create_user(
            username="editor-target",
            password="KeepPass@123",
            status="active",
        )
        original_password_hash = user.password

        form = UserForm(
            data={
                "username": "editor-target",
                "full_name": "Editor Target",
                "email": "editor@example.com",
                "phone_number": "13800138000",
                "status": "active",
                "is_staff": "on",
                "roles": [],
                "password": "",
            },
            instance=user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()

        self.assertEqual(user.password, original_password_hash)
        self.assertTrue(user.check_password("KeepPass@123"))


@override_settings(
    LOGIN_RATE_LIMIT_WINDOW_SECONDS=600,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "accounts-concurrency-tests-cache",
        }
    },
)
class LoginCounterConcurrencyTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_register_login_failure_is_consistent_under_concurrency(self):
        username = "counter-user"
        ip_address = "10.10.10.10"
        total_attempts = 120
        workers = 40

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda _: register_login_failure(username, ip_address), range(total_attempts)))

        self.assertEqual(int(cache.get(user_failure_key(username)) or 0), total_attempts)
        self.assertEqual(int(cache.get(ip_rate_limit_key(ip_address)) or 0), total_attempts)
        self.assertEqual(
            int(cache.get(ip_user_rate_limit_key(ip_address, username)) or 0),
            total_attempts,
        )


class UserDeleteViewTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.admin_user = self.user_model.objects.create_superuser(
            username="root-admin",
            password="Admin@123456",
            email="root@example.com",
        )
        self.target_user = self.user_model.objects.create_user(
            username="delete-target",
            password="Target@123456",
            is_staff=True,
            status="active",
        )

    def test_superuser_can_delete_user_from_edit_endpoint(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("accounts:user-edit", kwargs={"pk": self.target_user.pk}),
            data={"_action": "delete"},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("accounts:user-list"), fetch_redirect_response=False)
        self.assertFalse(self.user_model.objects.filter(pk=self.target_user.pk).exists())

    def test_cannot_delete_current_login_user(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("accounts:user-edit", kwargs={"pk": self.admin_user.pk}),
            data={"_action": "delete"},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("accounts:user-edit", kwargs={"pk": self.admin_user.pk}),
            fetch_redirect_response=False,
        )
        self.assertTrue(self.user_model.objects.filter(pk=self.admin_user.pk).exists())

    def test_post_delete_without_delete_permission_is_forbidden(self):
        manager = self.user_model.objects.create_user(
            username="manager-only-change",
            password="Manager@123456",
            is_staff=True,
            status="active",
        )
        change_permission = Permission.objects.get(codename="change_user")
        manager.user_permissions.add(change_permission)

        self.client.force_login(manager)
        response = self.client.post(
            reverse("accounts:user-edit", kwargs={"pk": self.target_user.pk}),
            data={"_action": "delete"},
            follow=False,
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.user_model.objects.filter(pk=self.target_user.pk).exists())
