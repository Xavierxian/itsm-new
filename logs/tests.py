from django.contrib.auth import get_user_model
from django.test import TestCase

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
