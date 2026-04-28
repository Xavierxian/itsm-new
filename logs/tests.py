from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from logs.models import LoginLog
from logs.utils import log_login_attempt
from logs.utils import serialize_instance


class SerializeInstanceTests(TestCase):
    def test_serialize_instance_excludes_sensitive_user_password(self):
        user = get_user_model()(
            username="sec-user",
            password="pbkdf2_sha256$xxxx",
            email="sec@example.com",
        )
        payload = serialize_instance(user)
        self.assertNotIn("password", payload)
        self.assertEqual(payload.get("username"), "sec-user")


class LoginIpCaptureTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_login_log_uses_client_chain_private_and_public_ip(self):
        request = self.factory.post(
            "/accounts/login/",
            HTTP_X_FORWARDED_FOR="192.168.10.21, 114.28.152.98",
            REMOTE_ADDR="10.0.0.9",
            HTTP_USER_AGENT="pytest-agent",
        )
        log_login_attempt(request=request, success=True, username="ip-user")
        row = LoginLog.objects.latest("id")
        self.assertEqual(row.ip_address, "192.168.10.21")
        self.assertEqual(row.private_ip, "192.168.10.21")
        self.assertEqual(row.public_ip, "114.28.152.98")

    def test_login_log_uses_public_remote_addr_when_no_forwarded_chain(self):
        request = self.factory.post(
            "/accounts/login/",
            REMOTE_ADDR="8.8.8.8",
            HTTP_USER_AGENT="pytest-agent",
        )
        log_login_attempt(request=request, success=False, username="ip-user-2")
        row = LoginLog.objects.latest("id")
        self.assertEqual(row.ip_address, "8.8.8.8")
        self.assertIsNone(row.private_ip)
        self.assertEqual(row.public_ip, "8.8.8.8")
