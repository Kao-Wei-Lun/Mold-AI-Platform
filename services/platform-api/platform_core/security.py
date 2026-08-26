from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from collections.abc import Callable
from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

PUBLIC_API_PATHS = {
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/api/v1/security/preflight",
}
SAFE_METHODS = {"GET", "HEAD"}
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _configured_secret(value: str) -> bool:
    lowered = value.lower()
    return len(value) >= 32 and "change_me" not in lowered and "change-me" not in lowered


def _request_id(request: HttpRequest) -> str:
    supplied = request.headers.get("X-Request-ID", "")
    return supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())


def _error_response(
    code: str,
    message: str,
    status: int,
    request_id: str,
    *,
    required_scope: str | None = None,
) -> JsonResponse:
    response = JsonResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": False,
                "request_id": request_id,
            }
        },
        status=status,
    )
    if status == 401:
        scope = f', scope="{required_scope}"' if required_scope else ""
        response["WWW-Authenticate"] = f'Bearer realm="mold-ai-demo"{scope}'
    response["Cache-Control"] = "no-store"
    return response


def _audit_denial(
    request: HttpRequest,
    *,
    request_id: str,
    code: str,
    required_scope: str | None,
) -> None:
    try:
        from .models import AuditEvent

        detail = {
            "request_id": request_id,
            "method": request.method,
            "path": request.path[:512],
            "decision": "deny",
            "reason_code": code,
            "required_scope": required_scope,
            "client_type": request.headers.get("X-Mold-AI-Client", "browser")[:64],
        }
        digest = hashlib.sha256(
            f"{request_id}:{request.method}:{request.path}:{code}".encode()
        ).hexdigest()
        AuditEvent.objects.create(
            event_type="security.access_denied.v1",
            actor_id="unauthenticated",
            target_refs=[f"api-path:{request.path[:256]}"],
            detail=detail,
            payload_hash=digest,
        )
    except Exception:
        # Authentication must fail closed even when the audit store is unavailable.
        return


def security_preflight_payload(request: HttpRequest) -> dict[str, object]:
    auth_mode = settings.DEMO_AUTH_MODE
    token_configured = _configured_secret(settings.DEMO_API_TOKEN)
    external_mode = settings.APP_ENV not in {"development", "test"}
    cors_origins = list(settings.CORS_ALLOWED_ORIGINS)
    public_web_https = settings.PUBLIC_WEB_BASE_URL.startswith("https://")
    public_web_host = urlparse(settings.PUBLIC_WEB_BASE_URL).hostname or ""
    allowed_hosts = set(settings.ALLOWED_HOSTS)
    public_mcp_https = bool(
        settings.PUBLIC_MCP_BASE_URL
    ) and settings.PUBLIC_MCP_BASE_URL.startswith("https://")
    tunnel_configured = bool(settings.SECURE_MCP_TUNNEL_ID) and not any(
        marker in settings.SECURE_MCP_TUNNEL_ID.lower() for marker in ("change_me", "change-me")
    )
    checks = {
        "external_environment_selected": external_mode,
        "auth_mode_valid": auth_mode in {"disabled", "required"},
        "api_token_configured": auth_mode != "required" or token_configured,
        "demo_scopes_complete": {"public-demo:read", "public-demo:write"}
        <= settings.DEMO_API_TOKEN_SCOPES,
        "debug_disabled": not settings.DEBUG,
        "secret_key_hardened": _configured_secret(settings.SECRET_KEY)
        and settings.SECRET_KEY != "unsafe-development-key",
        "allowed_hosts_hardened": bool(allowed_hosts)
        and "*" not in allowed_hosts
        and bool(public_web_host)
        and public_web_host in allowed_hosts,
        "https_proxy_trusted": settings.TRUST_PROXY_HEADERS,
        "ssl_redirect_enabled": settings.SECURE_SSL_REDIRECT,
        "secure_cookies_enabled": settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE,
        "hsts_enabled": settings.SECURE_HSTS_SECONDS > 0,
        "cors_https_only": bool(cors_origins)
        and all(origin.startswith("https://") for origin in cors_origins),
        "public_web_https": public_web_https,
        "mcp_connection_configured": public_mcp_https or tunnel_configured,
    }
    required_for_external = [
        "external_environment_selected",
        "auth_mode_valid",
        "api_token_configured",
        "demo_scopes_complete",
        "debug_disabled",
        "secret_key_hardened",
        "allowed_hosts_hardened",
        "https_proxy_trusted",
        "ssl_redirect_enabled",
        "secure_cookies_enabled",
        "hsts_enabled",
        "cors_https_only",
        "public_web_https",
        "mcp_connection_configured",
    ]
    production_ready = auth_mode == "required" and all(
        bool(checks[name]) for name in required_for_external
    )
    return {
        "schema_version": "1.0",
        "environment": settings.APP_ENV,
        "auth": {
            "mode": auth_mode,
            "required": auth_mode == "required",
            "token_configured": token_configured,
            "scopes": sorted(settings.DEMO_API_TOKEN_SCOPES),
        },
        "request_security": {
            "is_secure": request.is_secure(),
            "trusted_proxy_headers": settings.TRUST_PROXY_HEADERS,
        },
        "mcp": {
            "public_https_configured": public_mcp_https,
            "secure_tunnel_configured": tunnel_configured,
            "recommended_demo_path": "secure_mcp_tunnel",
            "oauth_implemented": False,
        },
        "checks": checks,
        "external_mode": external_mode,
        "production_ready": production_ready,
        "limitations": [
            "Static Demo bearer tokens are for controlled demonstrations, not enterprise SSO.",
            "Public ChatGPT MCP with user data requires OAuth 2.1; this stage does not fake it.",
            "Secure MCP Tunnel availability still depends on OpenAI account and workspace policy.",
        ],
    }


class DemoAccessMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = _request_id(request)
        request.mold_ai_request_id = request_id
        request.mold_ai_actor_id = "anonymous"
        request.mold_ai_scopes = set()

        response: HttpResponse
        if self._requires_authentication(request):
            response = self._authenticate(request, request_id)
        else:
            response = self.get_response(request)

        response["X-Request-ID"] = request_id
        response["X-Content-Type-Options"] = "nosniff"
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @staticmethod
    def _requires_authentication(request: HttpRequest) -> bool:
        return (
            settings.DEMO_AUTH_MODE == "required"
            and request.path.startswith("/api/v1/")
            and request.path not in PUBLIC_API_PATHS
            and request.method != "OPTIONS"
        )

    def _authenticate(self, request: HttpRequest, request_id: str) -> HttpResponse:
        required_scope = (
            "public-demo:read" if request.method in SAFE_METHODS else "public-demo:write"
        )
        configured_token = settings.DEMO_API_TOKEN
        if not _configured_secret(configured_token):
            return _error_response(
                "AUTH_CONFIGURATION_ERROR",
                "Demo authentication is required but no strong access token is configured.",
                503,
                request_id,
            )

        authorization = request.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token:
            _audit_denial(
                request,
                request_id=request_id,
                code="AUTH_TOKEN_REQUIRED",
                required_scope=required_scope,
            )
            return _error_response(
                "AUTH_TOKEN_REQUIRED",
                "A Demo bearer token is required.",
                401,
                request_id,
                required_scope=required_scope,
            )
        if not secrets.compare_digest(token, configured_token):
            _audit_denial(
                request,
                request_id=request_id,
                code="AUTH_TOKEN_INVALID",
                required_scope=required_scope,
            )
            return _error_response(
                "AUTH_TOKEN_INVALID",
                "The Demo bearer token is invalid.",
                401,
                request_id,
                required_scope=required_scope,
            )
        if required_scope not in settings.DEMO_API_TOKEN_SCOPES:
            _audit_denial(
                request,
                request_id=request_id,
                code="PERMISSION_SCOPE_REQUIRED",
                required_scope=required_scope,
            )
            return _error_response(
                "PERMISSION_SCOPE_REQUIRED",
                "The Demo token does not grant the required operation scope.",
                403,
                request_id,
                required_scope=required_scope,
            )

        request.mold_ai_actor_id = settings.DEMO_API_ACTOR_ID
        request.mold_ai_scopes = set(settings.DEMO_API_TOKEN_SCOPES)
        return self.get_response(request)
