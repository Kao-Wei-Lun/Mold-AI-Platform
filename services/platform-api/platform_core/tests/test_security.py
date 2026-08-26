from django.test import TestCase, override_settings

from platform_core.models import AuditEvent

STRONG_TOKEN = "stage10-demo-token-0123456789abcdef"


@override_settings(
    DEMO_AUTH_MODE="required",
    DEMO_API_TOKEN=STRONG_TOKEN,
    DEMO_API_TOKEN_SCOPES={"public-demo:read", "public-demo:write"},
    DEMO_API_ACTOR_ID="stage10-test-user",
)
class DemoAccessMiddlewareTests(TestCase):
    def test_health_and_preflight_remain_public(self) -> None:
        live = self.client.get("/api/v1/health/live")
        preflight = self.client.get("/api/v1/security/preflight")

        self.assertEqual(live.status_code, 200)
        self.assertEqual(preflight.status_code, 200)
        self.assertTrue(preflight.json()["auth"]["required"])
        self.assertTrue(preflight.json()["auth"]["token_configured"])
        self.assertTrue(live["X-Request-ID"])
        self.assertEqual(live["X-Content-Type-Options"], "nosniff")
        self.assertIn("camera=()", live["Permissions-Policy"])

    def test_missing_and_invalid_tokens_fail_closed_and_are_audited(self) -> None:
        missing = self.client.get("/api/v1/system/info", HTTP_X_REQUEST_ID="stage10-request-1")
        invalid = self.client.get(
            "/api/v1/system/info", HTTP_AUTHORIZATION="Bearer definitely-not-valid"
        )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json()["error"]["code"], "AUTH_TOKEN_REQUIRED")
        self.assertEqual(missing.json()["error"]["request_id"], "stage10-request-1")
        self.assertIn("public-demo:read", missing["WWW-Authenticate"])
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(invalid.json()["error"]["code"], "AUTH_TOKEN_INVALID")
        denials = AuditEvent.objects.filter(event_type="security.access_denied.v1")
        self.assertEqual(denials.count(), 2)
        self.assertNotIn("definitely-not-valid", str(list(denials.values("detail"))))

    def test_valid_token_allows_request_and_preserves_safe_request_id(self) -> None:
        response = self.client.get(
            "/api/v1/system/info",
            HTTP_AUTHORIZATION=f"Bearer {STRONG_TOKEN}",
            HTTP_X_REQUEST_ID="client-correlation-123",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Mold AI Platform")
        self.assertEqual(response["X-Request-ID"], "client-correlation-123")

    @override_settings(DEMO_API_TOKEN_SCOPES={"public-demo:read"})
    def test_read_only_token_cannot_call_write_endpoint(self) -> None:
        response = self.client.post(
            "/api/v1/assistant/messages",
            {"message": "hello", "context": {"context_version": "1.0"}},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {STRONG_TOKEN}",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "PERMISSION_SCOPE_REQUIRED")
        denial = AuditEvent.objects.get(event_type="security.access_denied.v1")
        self.assertEqual(denial.detail["required_scope"], "public-demo:write")

    @override_settings(DEMO_API_TOKEN="short")
    def test_required_mode_without_strong_token_returns_configuration_error(self) -> None:
        response = self.client.get("/api/v1/system/info")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "AUTH_CONFIGURATION_ERROR")

    @override_settings(DEMO_API_TOKEN="CHANGE_ME-use-at-least-32-random-characters")
    def test_required_mode_rejects_placeholder_token(self) -> None:
        response = self.client.get("/api/v1/system/info")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "AUTH_CONFIGURATION_ERROR")


class SecurityPreflightTests(TestCase):
    @override_settings(
        APP_ENV="release",
        DEBUG=False,
        SECRET_KEY="release-secret-key-0123456789abcdef",
        ALLOWED_HOSTS=["mold.example.test", "api", "testserver"],
        DEMO_AUTH_MODE="required",
        DEMO_API_TOKEN=STRONG_TOKEN,
        DEMO_API_TOKEN_SCOPES={"public-demo:read", "public-demo:write"},
        TRUST_PROXY_HEADERS=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=31536000,
        CORS_ALLOWED_ORIGINS=["https://mold.example.test"],
        PUBLIC_WEB_BASE_URL="https://mold.example.test",
        PUBLIC_MCP_BASE_URL="",
        SECURE_MCP_TUNNEL_ID="tunnel_example",
    )
    def test_release_preflight_reports_ready_without_exposing_secrets(self) -> None:
        response = self.client.get("/api/v1/security/preflight", HTTP_X_FORWARDED_PROTO="https")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["production_ready"])
        self.assertTrue(payload["request_security"]["is_secure"])
        self.assertTrue(payload["mcp"]["secure_tunnel_configured"])
        self.assertFalse(payload["mcp"]["oauth_implemented"])
        self.assertNotIn(STRONG_TOKEN, str(payload))

    def test_local_defaults_are_explicitly_not_production_ready(self) -> None:
        response = self.client.get("/api/v1/security/preflight")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["production_ready"])
        self.assertEqual(payload["auth"]["mode"], "disabled")
