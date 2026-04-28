import base64
import hashlib
import re
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

SENSITIVE_FIELD_NAMES = {
    "password",
    "boot_password",
    "login_password",
    "token",
    "secret",
    "api_key",
    "access_key",
    "access_key_id",
    "access_key_secret",
    "authorization",
}
SENSITIVE_KEYWORDS = ("password", "secret", "token", "key", "authorization")
SENSITIVE_QUERY_PATTERN = re.compile(
    r"((?:password|secret|token|key|authorization)[^=&\s]{0,32}=)([^&\s]+)",
    flags=re.IGNORECASE,
)


def _looks_sensitive(name):
    lowered = str(name or "").strip().lower()
    return bool(lowered and (lowered in SENSITIVE_FIELD_NAMES or any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)))


def redact_text(value):
    text = str(value or "")
    if not text:
        return text
    return SENSITIVE_QUERY_PATTERN.sub(r"\1***", text)


def redact_mapping(payload):
    if not isinstance(payload, dict):
        return payload
    sanitized = {}
    for key, value in payload.items():
        if _looks_sensitive(key):
            sanitized[key] = "***"
            continue
        if isinstance(value, dict):
            sanitized[key] = redact_mapping(value)
            continue
        if isinstance(value, (list, tuple)):
            sanitized[key] = [redact_text(item) for item in value]
            continue
        sanitized[key] = redact_text(value)
    return sanitized


def is_sensitive_field(field_name):
    return _looks_sensitive(field_name)


@lru_cache(maxsize=1)
def _build_fernet():
    key = str(getattr(settings, "FIELD_ENCRYPTION_KEY", "") or "").strip()
    if key:
        return Fernet(key.encode("utf-8"))
    digest = hashlib.sha256(str(settings.SECRET_KEY).encode("utf-8")).digest()
    derived_key = base64.urlsafe_b64encode(digest)
    return Fernet(derived_key)


def encrypt_secret(value):
    text = str(value or "").strip()
    if not text:
        return ""
    token = _build_fernet().encrypt(text.encode("utf-8")).decode("utf-8")
    return f"enc:{token}"


def decrypt_secret(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.startswith("enc:"):
        return text
    token = text[4:]
    try:
        return _build_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
