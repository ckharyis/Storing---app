import os
from decimal import Decimal
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEMO_MODE = env_bool("DEMO_MODE", True)
DEBUG = env_bool("DEBUG", DEMO_MODE)
SECRET_KEY = os.getenv("SECRET_KEY", "demo-only-change-me-" + "x" * 48)

if not DEMO_MODE and (len(SECRET_KEY) < 50 or SECRET_KEY.startswith("demo-only")):
    raise ImproperlyConfigured("Production requires a random SECRET_KEY of at least 50 characters.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "http://localhost:8000").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "portal.middleware.SecurityHeadersMiddleware",
    "portal.middleware.NoCacheSensitiveMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "portal.context_processors.portal_context",
            ],
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=env_bool("DATABASE_SSL_REQUIRED", not DEMO_MODE),
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("nl", "Nederlands"), ("pap", "Papiamentu")]
TIME_ZONE = "America/Curacao"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/protected-media/"
MEDIA_ROOT = BASE_DIR / "protected_media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedStaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

USE_S3 = env_bool("USE_S3", False)
if USE_S3:
    INSTALLED_APPS.append("storages")
    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}
    AWS_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL") or None
    AWS_S3_REGION_NAME = os.getenv("S3_REGION", "auto")
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 300
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_OBJECT_PARAMETERS = {"ServerSideEncryption": "AES256"}

EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend"
    if DEMO_MODE
    else "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@example.invalid")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEMO_MODE
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_AGE = 1800
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SECURE = not DEMO_MODE
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_HTTPONLY = True
SECURE_SSL_REDIRECT = not DEMO_MODE
SECURE_HSTS_SECONDS = 31536000 if not DEMO_MODE else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEMO_MODE
SECURE_HSTS_PRELOAD = not DEMO_MODE
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PUBLIC_BRAND_NAME = os.getenv("PUBLIC_BRAND_NAME", "Lending Application Portal")
BUSINESS_LEGAL_NAME = os.getenv("BUSINESS_LEGAL_NAME", "[Legal lender name required]")
BUSINESS_ADDRESS = os.getenv("BUSINESS_ADDRESS", "[Registered address required]")
BUSINESS_REGISTRATION_NUMBER = os.getenv("BUSINESS_REGISTRATION_NUMBER", "[Registration number required]")
LENDER_AUTHORIZATION_REFERENCE = os.getenv("LENDER_AUTHORIZATION_REFERENCE", "[CBCS authorization status required]")
BUSINESS_CONTACT_EMAIL = os.getenv("BUSINESS_CONTACT_EMAIL", DEFAULT_FROM_EMAIL)
PRODUCTION_COMPLIANCE_ACK = os.getenv("PRODUCTION_COMPLIANCE_ACK", "")

MAX_APR = Decimal(os.getenv("MAX_APR", "27.00"))
MIN_LOAN_AMOUNT = Decimal(os.getenv("MIN_LOAN_AMOUNT", "50.00"))
MAX_LOAN_AMOUNT = Decimal(os.getenv("MAX_LOAN_AMOUNT", "10000.00"))
TERMS_VERSION = "2026-08-draft"
PRIVACY_VERSION = "2026-08-draft"
CONTRACT_TEMPLATE_VERSION = "nl-source-derived-v1-legal-review-required"

MFA_ENCRYPTION_KEY = os.getenv("MFA_ENCRYPTION_KEY", SECRET_KEY)
IP_HASH_KEY = os.getenv("IP_HASH_KEY", SECRET_KEY)
TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS", False)
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")

if not DEMO_MODE:
    required = {
        "BUSINESS_LEGAL_NAME": BUSINESS_LEGAL_NAME,
        "BUSINESS_ADDRESS": BUSINESS_ADDRESS,
        "BUSINESS_REGISTRATION_NUMBER": BUSINESS_REGISTRATION_NUMBER,
        "LENDER_AUTHORIZATION_REFERENCE": LENDER_AUTHORIZATION_REFERENCE,
        "BUSINESS_CONTACT_EMAIL": BUSINESS_CONTACT_EMAIL,
        "MFA_ENCRYPTION_KEY": os.getenv("MFA_ENCRYPTION_KEY", ""),
        "IP_HASH_KEY": os.getenv("IP_HASH_KEY", ""),
        "TURNSTILE_SITE_KEY": TURNSTILE_SITE_KEY,
        "TURNSTILE_SECRET_KEY": TURNSTILE_SECRET_KEY,
        "EMAIL_HOST": EMAIL_HOST,
        "EMAIL_HOST_USER": EMAIL_HOST_USER,
        "EMAIL_HOST_PASSWORD": EMAIL_HOST_PASSWORD,
        "S3_ACCESS_KEY_ID": os.getenv("S3_ACCESS_KEY_ID", ""),
        "S3_SECRET_ACCESS_KEY": os.getenv("S3_SECRET_ACCESS_KEY", ""),
        "S3_BUCKET_NAME": os.getenv("S3_BUCKET_NAME", ""),
    }
    missing = [name for name, value in required.items() if not value or value.startswith("[")]
    if missing:
        raise ImproperlyConfigured("Missing production settings: " + ", ".join(missing))
    if PRODUCTION_COMPLIANCE_ACK != "CONFIRMED":
        raise ImproperlyConfigured("Set PRODUCTION_COMPLIANCE_ACK=CONFIRMED only after legal/compliance review.")
    if not USE_S3:
        raise ImproperlyConfigured("Production requires private object storage (USE_S3=true).")

LOGIN_URL = "/staff/login/"
