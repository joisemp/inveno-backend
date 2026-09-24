"""
Production settings — deployed on Railway.
DB and Redis are managed services; static/media served from DigitalOcean Spaces.
"""
import os

import dj_database_url
from decouple import config

from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Database — single URL from Railway / managed Postgres
# ---------------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL"),
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True,
    )
}

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
DEBUG = False
SEED_DEMO = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
REFRESH_TOKEN_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# Email — configure via env vars (any SMTP provider)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")

# ---------------------------------------------------------------------------
# DigitalOcean Spaces — static & media storage
# ---------------------------------------------------------------------------
_DO_KEY = config("DO_SPACES_KEY")
_DO_SECRET = config("DO_SPACES_SECRET")
_DO_BUCKET = config("DO_SPACES_BUCKET")
_DO_REGION = config("DO_SPACES_REGION", default="nyc3")
_DO_ENDPOINT = config(
    "DO_SPACES_ENDPOINT_URL",
    default=f"https://{_DO_REGION}.digitaloceanspaces.com",
)
_DO_CUSTOM_DOMAIN = config("DO_SPACES_CUSTOM_DOMAIN", default=None)

_STATIC_PREFIX = config("DO_SPACES_STATIC_PREFIX", default="static/")
_MEDIA_PREFIX = config("DO_SPACES_MEDIA_PREFIX", default="media/")

# Build CDN base URL
if _DO_CUSTOM_DOMAIN:
    _CDN_BASE = f"https://{_DO_CUSTOM_DOMAIN}"
else:
    _CDN_BASE = f"https://{_DO_BUCKET}.{_DO_REGION}.digitaloceanspaces.com"

STATIC_URL = f"{_CDN_BASE}/{_STATIC_PREFIX}"
MEDIA_URL = f"{_CDN_BASE}/{_MEDIA_PREFIX}"

# Shared Spaces config passed to both backends
_SPACES_CONFIG = {
    "bucket_name": _DO_BUCKET,
    "access_key": _DO_KEY,
    "secret_key": _DO_SECRET,
    "endpoint_url": _DO_ENDPOINT,
    "region_name": _DO_REGION,
    "default_acl": "public-read",
    "file_overwrite": False,
    "custom_domain": _DO_CUSTOM_DOMAIN,
    "querystring_auth": False,
    "signature_version": "s3v4",
}

STORAGES = {
    "default": {
        # Media files
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            **_SPACES_CONFIG,
            "location": _MEDIA_PREFIX.rstrip("/"),
        },
    },
    "staticfiles": {
        # Static files — overwrite so collectstatic can replace the manifest
        "BACKEND": "storages.backends.s3boto3.S3ManifestStaticStorage",
        "OPTIONS": {
            **_SPACES_CONFIG,
            "location": _STATIC_PREFIX.rstrip("/"),
            "file_overwrite": True,
        },
    },
}

# ---------------------------------------------------------------------------
# Logging — structured JSON for Railway log viewer
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Sentry (optional — set SENTRY_DSN env var to enable)
# ---------------------------------------------------------------------------
_SENTRY_DSN = config("SENTRY_DSN", default=None)
if _SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
