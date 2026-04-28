from pathlib import Path
import os
import sys
from urllib.parse import quote

from celery.schedules import crontab
import pymysql
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

pymysql.install_as_MySQLdb()

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

RUNTIME_DIR = BASE_DIR / "runtime"
LOG_DIR = RUNTIME_DIR / "logs"
RUNTIME_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-dev-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
DJANGO_ENV = os.getenv("DJANGO_ENV", "development").strip().lower() or "development"
IS_PRODUCTION = DJANGO_ENV in {"prod", "production"}
IS_TEST = any(arg in {"test", "pytest"} for arg in sys.argv)
if IS_PRODUCTION and (not SECRET_KEY or SECRET_KEY == "unsafe-dev-secret-key"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a strong value in production.")
if IS_PRODUCTION and DEBUG:
    raise ImproperlyConfigured("DJANGO_DEBUG must be false in production.")


def env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


SERVE_STATIC_WITH_DJANGO = env_bool("SERVE_STATIC_WITH_DJANGO", IS_PRODUCTION)


def build_redis_url():
    direct_url = str(os.getenv("REDIS_URL", "") or "").strip()
    if direct_url:
        return direct_url

    host = str(os.getenv("REDIS_HOST", "") or "").strip()
    if not host:
        return ""

    port = str(os.getenv("REDIS_PORT", "6379") or "6379").strip()
    db = str(os.getenv("REDIS_DB", "0") or "0").strip()
    username = str(os.getenv("REDIS_USERNAME", "") or "").strip()
    password = str(os.getenv("REDIS_PASSWORD", "") or "")

    auth_segment = ""
    if username or password:
        encoded_user = quote(username, safe="")
        encoded_password = quote(password, safe="")
        if username:
            auth_segment = f"{encoded_user}:{encoded_password}@"
        else:
            auth_segment = f":{encoded_password}@"

    return f"redis://{auth_segment}{host}:{port}/{db}"

_allowed_hosts_raw = os.getenv("DJANGO_ALLOWED_HOSTS", "")
_csrf_origins_raw = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "")
ALLOWED_HOSTS = [host.strip() for host in (_allowed_hosts_raw or "127.0.0.1,localhost").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in (_csrf_origins_raw or "").split(",") if origin.strip()]
if IS_PRODUCTION and not _allowed_hosts_raw.strip():
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS is required when DJANGO_ENV=production.")
if IS_PRODUCTION and not _csrf_origins_raw.strip():
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS is required when DJANGO_ENV=production.")

# Dev-friendly CSRF defaults: include loopback origins with/without explicit port.
_local_csrf_defaults = [
    "http://127.0.0.1",
    "http://localhost",
    "https://127.0.0.1",
    "https://localhost",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "https://127.0.0.1:8000",
    "https://localhost:8000",
]
if not IS_PRODUCTION:
    for _origin in _local_csrf_defaults:
        if _origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(_origin)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_htmx",
    "csp",
    "core",
    "accounts",
    "assets",
    "mappings",
    "bsecp",
    "cloudops",
    "monitoring",
    "logs",
]

MIDDLEWARE = ["django.middleware.security.SecurityMiddleware"]
if SERVE_STATIC_WITH_DJANGO:
    MIDDLEWARE.append("whitenoise.middleware.WhiteNoiseMiddleware")
MIDDLEWARE += [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "csp.middleware.CSPMiddleware",
    "core.middleware.RequestContextMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if os.getenv("MYSQL_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("MYSQL_DB"),
            "USER": os.getenv("MYSQL_USER"),
            "PASSWORD": os.getenv("MYSQL_PASSWORD"),
            "HOST": os.getenv("MYSQL_HOST", "127.0.0.1"),
            "PORT": os.getenv("MYSQL_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            "CONN_MAX_AGE": int(os.getenv("DJANGO_DB_CONN_MAX_AGE", "300")),
            "CONN_HEALTH_CHECKS": env_bool("DJANGO_DB_CONN_HEALTH_CHECKS", True),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "CONN_MAX_AGE": int(os.getenv("DJANGO_SQLITE_CONN_MAX_AGE", "0")),
            "CONN_HEALTH_CHECKS": env_bool("DJANGO_SQLITE_CONN_HEALTH_CHECKS", False),
        }
    }

MYSQL_AUTH = {
    "HOST": os.getenv("MYSQL_AUTH_HOST", ""),
    "PORT": int(os.getenv("MYSQL_AUTH_PORT", "3306")),
    "USER": os.getenv("MYSQL_AUTH_USER", ""),
    "PASSWORD": os.getenv("MYSQL_AUTH_PASSWORD", ""),
    "NAME": os.getenv("MYSQL_AUTH_DB", ""),
    "LOGIN_TIMEOUT": int(os.getenv("MYSQL_AUTH_LOGIN_TIMEOUT", "5")),
    "QUERY_TIMEOUT": int(os.getenv("MYSQL_AUTH_QUERY_TIMEOUT", "20")),
    "CHARSET": os.getenv("MYSQL_AUTH_CHARSET", "utf8"),
}

SQLSERVER_AUTH = {
    "HOST": os.getenv("SQLSERVER_AUTH_HOST", ""),
    "PORT": int(os.getenv("SQLSERVER_AUTH_PORT", "1433")),
    "USER": os.getenv("SQLSERVER_AUTH_USER", ""),
    "PASSWORD": os.getenv("SQLSERVER_AUTH_PASSWORD", ""),
    "NAME": os.getenv("SQLSERVER_AUTH_DB", ""),
    "LOGIN_TIMEOUT": int(os.getenv("SQLSERVER_AUTH_LOGIN_TIMEOUT", "5")),
    "QUERY_TIMEOUT": int(os.getenv("SQLSERVER_AUTH_QUERY_TIMEOUT", "20")),
    "CHARSET": os.getenv("SQLSERVER_AUTH_CHARSET", "utf8"),
    "TDS_VERSION": os.getenv("SQLSERVER_AUTH_TDS_VERSION", "7.0"),
}

MONITORING_PROMETHEUS_URL = os.getenv("MONITORING_PROMETHEUS_URL", "https://127.0.0.1:9090")
MONITORING_REQUEST_TIMEOUT_SECONDS = int(os.getenv("MONITORING_REQUEST_TIMEOUT_SECONDS", "15"))
MONITORING_REQUEST_RETRIES = int(os.getenv("MONITORING_REQUEST_RETRIES", "2"))
MONITORING_HTTP_POOL_MAXSIZE = int(os.getenv("MONITORING_HTTP_POOL_MAXSIZE", "32"))
MONITORING_HOST_SNAPSHOT_CACHE_SECONDS = int(os.getenv("MONITORING_HOST_SNAPSHOT_CACHE_SECONDS", "15"))
MONITORING_VERIFY_TLS = env_bool("MONITORING_VERIFY_TLS", True)
ALLOW_INSECURE_UPSTREAM_HTTP = env_bool("ALLOW_INSECURE_UPSTREAM_HTTP", False)
MONITORING_K8S_DB = {
    "HOST": os.getenv("MONITORING_K8S_DB_HOST", os.getenv("MYSQL_HOST", "127.0.0.1")),
    "PORT": int(os.getenv("MONITORING_K8S_DB_PORT", os.getenv("MYSQL_PORT", "3306"))),
    "USER": os.getenv("MONITORING_K8S_DB_USER", os.getenv("MYSQL_USER", "")),
    "PASSWORD": os.getenv("MONITORING_K8S_DB_PASSWORD", os.getenv("MYSQL_PASSWORD", "")),
    "NAME": os.getenv("MONITORING_K8S_DB_NAME", os.getenv("MYSQL_DB", "")),
    "CHARSET": os.getenv("MONITORING_K8S_DB_CHARSET", "utf8mb4"),
    "CONNECT_TIMEOUT": int(os.getenv("MONITORING_K8S_DB_CONNECT_TIMEOUT", "6")),
    "READ_TIMEOUT": int(os.getenv("MONITORING_K8S_DB_READ_TIMEOUT", "20")),
    "WRITE_TIMEOUT": int(os.getenv("MONITORING_K8S_DB_WRITE_TIMEOUT", "20")),
}
MONITORING_AI = {
    "ENABLED": os.getenv("MONITORING_AI_ENABLED", "False").lower() == "true",
    "BASE_URL": os.getenv("MONITORING_AI_BASE_URL", os.getenv("OPENAI_BASE_URL", "")).strip(),
    "API_KEY": os.getenv("MONITORING_AI_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip(),
    "MODEL": os.getenv("MONITORING_AI_MODEL", os.getenv("OPENAI_MODEL", "")).strip(),
    "TIMEOUT_SECONDS": int(os.getenv("MONITORING_AI_TIMEOUT_SECONDS", "20")),
    "MAX_ROWS": int(os.getenv("MONITORING_AI_MAX_ROWS", "120")),
    "VERIFY_TLS": env_bool("MONITORING_AI_VERIFY_TLS", True),
}
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "").strip()

# Email (SMTP)
SMTP_SERVER = os.getenv("SMTP_SERVER", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USERNAME).strip()
FROM_NAME = os.getenv("FROM_NAME", "IT运维管理平台").strip()

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = SMTP_SERVER
EMAIL_PORT = SMTP_PORT
EMAIL_HOST_USER = SMTP_USERNAME
EMAIL_HOST_PASSWORD = SMTP_PASSWORD
EMAIL_USE_SSL = env_bool("SMTP_USE_SSL", SMTP_PORT == 465)
EMAIL_USE_TLS = env_bool("SMTP_USE_TLS", False)
EMAIL_SSL_CERTFILE = os.getenv("SMTP_SSL_CERTFILE", "").strip() or None
EMAIL_SSL_KEYFILE = os.getenv("SMTP_SSL_KEYFILE", "").strip() or None
if EMAIL_USE_SSL and EMAIL_USE_TLS:
    EMAIL_USE_TLS = False
EMAIL_TIMEOUT = int(os.getenv("SMTP_TIMEOUT_SECONDS", "15"))
DEFAULT_FROM_EMAIL = FROM_EMAIL or SMTP_USERNAME

MONITORING_ALERT_FROM_NAME = FROM_NAME or "IT运维管理平台"
MONITORING_ALERT_EMAIL_RECIPIENTS = os.getenv("MONITORING_ALERT_EMAIL_RECIPIENTS", "").strip()
MONITORING_ALERT_FIXED_CC = os.getenv(
    "MONITORING_ALERT_FIXED_CC",
    "xin.xian@baisonmail.com,gjb@baisonmail.com",
).strip()
MONITORING_ALERT_USER_EMAIL_TABLE = os.getenv("MONITORING_ALERT_USER_EMAIL_TABLE", "BS_DD_USER_BS").strip()
MONITORING_ALERT_USER_NAME_COLUMN = os.getenv("MONITORING_ALERT_USER_NAME_COLUMN", "name").strip()
MONITORING_ALERT_USER_EMAIL_COLUMN = os.getenv("MONITORING_ALERT_USER_EMAIL_COLUMN", "email").strip()
MONITORING_DAILY_ALERT_EMAIL_ENABLED = os.getenv("MONITORING_DAILY_ALERT_EMAIL_ENABLED", "True").strip().lower() == "true"
MONITORING_DAILY_ALERT_EMAIL_HOUR = int(os.getenv("MONITORING_DAILY_ALERT_EMAIL_HOUR", "9"))
MONITORING_DAILY_ALERT_EMAIL_MINUTE = int(os.getenv("MONITORING_DAILY_ALERT_EMAIL_MINUTE", "0"))
MONITORING_DAILY_ALERT_THRESHOLD = float(os.getenv("MONITORING_DAILY_ALERT_THRESHOLD", "90"))

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "accounts.validators.UserAttributeSimilarityValidator"},
    {"NAME": "accounts.validators.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "accounts.validators.CommonPasswordValidator"},
    {"NAME": "accounts.validators.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
if SERVE_STATIC_WITH_DJANGO:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    WHITENOISE_MAX_AGE = int(os.getenv("WHITENOISE_MAX_AGE", "31536000" if IS_PRODUCTION else "60"))
    WHITENOISE_USE_FINDERS = not IS_PRODUCTION
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.RolePermissionBackend",
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", IS_PRODUCTION)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", IS_PRODUCTION)
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", IS_PRODUCTION)
_default_hsts_seconds = "31536000" if IS_PRODUCTION else "0"
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", _default_hsts_seconds))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", IS_PRODUCTION)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", IS_PRODUCTION)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
X_FRAME_OPTIONS = "DENY"

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": ("'self'",),
        "style-src": ("'self'",),
        "img-src": ("'self'", "data:"),
        "font-src": ("'self'", "data:"),
        "connect-src": ("'self'",),
        "object-src": ("'none'",),
        "frame-ancestors": ("'none'",),
    }
}

REDIS_URL = build_redis_url()
if REDIS_URL and not IS_TEST:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "TIMEOUT": int(os.getenv("DJANGO_CACHE_DEFAULT_TIMEOUT", "300")),
            "KEY_PREFIX": os.getenv("DJANGO_CACHE_KEY_PREFIX", "itsm"),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "itsm-dev-cache",
        }
    }

CELERY_BROKER_URL = REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = REDIS_URL or "cache+memory://"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = not bool(REDIS_URL)
CELERY_BEAT_SCHEDULE = {}
if MONITORING_DAILY_ALERT_EMAIL_ENABLED:
    CELERY_BEAT_SCHEDULE["monitoring-send-daily-partition-alert-email"] = {
        "task": "monitoring.send_daily_partition_alert_email",
        "schedule": crontab(
            hour=MONITORING_DAILY_ALERT_EMAIL_HOUR,
            minute=MONITORING_DAILY_ALERT_EMAIL_MINUTE,
        ),
    }

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

MESSAGE_TAGS = {
    10: "debug",
    20: "info",
    25: "success",
    30: "warning",
    40: "error",
}

LOGIN_FAILURE_LIMIT = int(os.getenv("LOGIN_FAILURE_LIMIT", "5"))
LOGIN_LOCK_MINUTES = int(os.getenv("LOGIN_LOCK_MINUTES", "15"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "600"))
LOGIN_RATE_LIMIT_PER_IP = int(os.getenv("LOGIN_RATE_LIMIT_PER_IP", "60"))
LOGIN_RATE_LIMIT_PER_IP_USER = int(os.getenv("LOGIN_RATE_LIMIT_PER_IP_USER", "10"))
DASHBOARD_STATS_CACHE_TTL = int(os.getenv("DASHBOARD_STATS_CACHE_TTL", "60"))
AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "365"))
APP_LOG_RETENTION_DAYS = int(os.getenv("APP_LOG_RETENTION_DAYS", "90"))
SECURITY_EVENT_RETENTION_DAYS = int(os.getenv("SECURITY_EVENT_RETENTION_DAYS", "180"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact_sensitive": {
            "()": "core.logging_filters.SensitiveDataFilter",
        }
    },
    "formatters": {
        "standard": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["redact_sensitive"],
        },
        "application_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "application.log",
            "formatter": "standard",
            "encoding": "utf-8",
            "maxBytes": int(os.getenv("APP_LOG_MAX_BYTES", str(20 * 1024 * 1024))),
            "backupCount": int(os.getenv("APP_LOG_BACKUP_COUNT", "10")),
            "filters": ["redact_sensitive"],
        },
    },
    "root": {
        "handlers": ["console", "application_file"],
        "level": "INFO",
    },
}
