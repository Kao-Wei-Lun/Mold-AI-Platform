import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-development-key")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,api,testserver").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "platform_core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "platform_core.security.DemoAccessMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "mold_platform.urls"

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
            ],
        },
    }
]

WSGI_APPLICATION = "mold_platform.wsgi.application"
ASGI_APPLICATION = "mold_platform.asgi.application"

if os.getenv("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "mold_ai"),
            "USER": os.getenv("POSTGRES_USER", "mold_ai"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "mold_ai_demo"),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hant"
TIME_ZONE = "Asia/Taipei"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(os.getenv("ARTIFACT_STORAGE_ROOT", BASE_DIR / ".runtime" / "artifacts"))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MAX_CAD_UPLOAD_BYTES = int(os.getenv("MAX_CAD_UPLOAD_BYTES", str(200 * 1024 * 1024)))
MAX_KNOWLEDGE_UPLOAD_BYTES = int(os.getenv("MAX_KNOWLEDGE_UPLOAD_BYTES", str(5 * 1024 * 1024)))
MAX_INGESTION_UPLOAD_BYTES = int(os.getenv("MAX_INGESTION_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_HMI_UPLOAD_BYTES = int(os.getenv("MAX_HMI_UPLOAD_BYTES", str(10 * 1024 * 1024)))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_CAD_UPLOAD_BYTES + (1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEMO_AUTH_MODE = os.getenv("DEMO_AUTH_MODE", "disabled").lower()
DEMO_API_TOKEN = os.getenv("DEMO_API_TOKEN", "")
DEMO_API_TOKEN_SCOPES = {
    scope.strip()
    for scope in os.getenv("DEMO_API_TOKEN_SCOPES", "public-demo:read,public-demo:write").split(",")
    if scope.strip()
}
DEMO_API_ACTOR_ID = os.getenv("DEMO_API_ACTOR_ID", "demo-access-key")
PLATFORM_SERVICE_TOKEN = os.getenv("PLATFORM_SERVICE_TOKEN", "")
PLATFORM_SERVICE_TOKEN_SCOPES = {
    scope.strip()
    for scope in os.getenv(
        "PLATFORM_SERVICE_TOKEN_SCOPES",
        "public-demo:read,public-demo:write",
    ).split(",")
    if scope.strip()
}
PLATFORM_SERVICE_ACTOR_ID = os.getenv(
    "PLATFORM_SERVICE_ACTOR_ID",
    "mcp-gateway-service",
)
PLATFORM_SERVICE_CLIENTS = {
    client.strip()
    for client in os.getenv("PLATFORM_SERVICE_CLIENTS", "mcp-gateway").split(",")
    if client.strip()
}
LOCAL_AUTH_MAX_FAILURES = int(os.getenv("LOCAL_AUTH_MAX_FAILURES", "5"))
LOCAL_AUTH_LOCK_SECONDS = int(os.getenv("LOCAL_AUTH_LOCK_SECONDS", "300"))
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = int(os.getenv("DJANGO_SESSION_COOKIE_AGE", "28800"))
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"
if TRUST_PROXY_HEADERS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "false").lower() == "true"
SESSION_COOKIE_SECURE = os.getenv("DJANGO_COOKIE_SECURE", "false").lower() == "true"
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = False
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("DJANGO_CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}

APP_NAME = "Mold AI Platform"
APP_ENV = os.getenv("APP_ENV", "development")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
PUBLIC_WEB_BASE_URL = os.getenv("PUBLIC_WEB_BASE_URL", "http://localhost:5173")
PUBLIC_MCP_BASE_URL = os.getenv("PUBLIC_MCP_BASE_URL", "")
SECURE_MCP_TUNNEL_ID = os.getenv("SECURE_MCP_TUNNEL_ID", "")
QUICK_TUNNEL_MODE = os.getenv("QUICK_TUNNEL_MODE", "false").lower() == "true"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", os.getenv("ASSISTANT_LLM_PROVIDER", "deterministic-demo"))
# Compatibility alias for Stage 6 deployments. New deployments use LLM_PROVIDER.
ASSISTANT_LLM_PROVIDER = LLM_PROVIDER
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_CAD_COLLECTION = os.getenv("QDRANT_CAD_COLLECTION", "cad-similarity-v1")
QDRANT_KNOWLEDGE_COLLECTION = os.getenv("QDRANT_KNOWLEDGE_COLLECTION", "knowledge-text-demo-v1")
SIMILARITY_INDEX_VERSION = os.getenv("SIMILARITY_INDEX_VERSION", "cad-demo-v1")
SIMILARITY_AUTO_INDEX = os.getenv("SIMILARITY_AUTO_INDEX", "false").lower() == "true"

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_TASK_DEFAULT_QUEUE = "general"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
