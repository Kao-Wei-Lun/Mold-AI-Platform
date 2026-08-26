from unittest.mock import patch

from django.test import TestCase


class HealthEndpointTests(TestCase):
    def test_liveness_endpoint(self) -> None:
        response = self.client.get("/api/v1/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "platform-api"})

    @patch("platform_core.views.collect_readiness")
    def test_readiness_endpoint_returns_ok(self, collect_readiness) -> None:
        collect_readiness.return_value = {
            "status": "ok",
            "services": [
                {"name": "database", "status": "ok", "detail": None},
                {"name": "redis", "status": "ok", "detail": None},
                {"name": "qdrant", "status": "ok", "detail": None},
            ],
        }

        response = self.client.get("/api/v1/health/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    @patch("platform_core.views.collect_readiness")
    def test_readiness_endpoint_returns_503_when_dependency_fails(self, collect_readiness) -> None:
        collect_readiness.return_value = {
            "status": "degraded",
            "services": [{"name": "qdrant", "status": "error", "detail": "timeout"}],
        }

        response = self.client.get("/api/v1/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "degraded")

    def test_system_info_does_not_expose_secrets(self) -> None:
        response = self.client.get("/api/v1/system/info")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Mold AI Platform")
        self.assertNotIn("secret", response.json())
