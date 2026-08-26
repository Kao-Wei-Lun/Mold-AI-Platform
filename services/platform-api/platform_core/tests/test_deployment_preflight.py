from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

STRONG_TOKEN = "stage10-demo-token-0123456789abcdef"


class DeploymentPreflightCommandTests(SimpleTestCase):
    def test_strict_mode_fails_for_local_development_defaults(self) -> None:
        with self.assertRaises(CommandError):
            call_command("deployment_preflight", "--strict", stdout=StringIO())

    @override_settings(
        APP_ENV="release",
        DEBUG=False,
        SECRET_KEY="release-secret-key-0123456789abcdef",
        ALLOWED_HOSTS=["mold.example.test", "api"],
        DEMO_AUTH_MODE="required",
        DEMO_API_TOKEN=STRONG_TOKEN,
        DEMO_API_TOKEN_SCOPES={"public-demo:read", "public-demo:write"},
        TRUST_PROXY_HEADERS=True,
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=31536000,
        CORS_ALLOWED_ORIGINS=["https://mold.example.test"],
        PUBLIC_WEB_BASE_URL="https://mold.example.test",
        PUBLIC_MCP_BASE_URL="",
        SECURE_MCP_TUNNEL_ID="tunnel_example",
    )
    def test_strict_mode_passes_for_hardened_release_configuration(self) -> None:
        output = StringIO()

        call_command("deployment_preflight", "--strict", "--json", stdout=output)

        self.assertIn('"production_ready": true', output.getvalue())
        self.assertNotIn(STRONG_TOKEN, output.getvalue())
