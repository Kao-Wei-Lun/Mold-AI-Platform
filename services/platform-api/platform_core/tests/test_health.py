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

    def test_engineering_capabilities_are_canonical_and_truthful(self) -> None:
        response = self.client.get("/api/v1/engineering-capabilities")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data_scope"], "public_demo")
        self.assertEqual(len(body["capabilities"]), 8)
        process = next(
            item for item in body["capabilities"] if item["capability_id"] == "process.case_search"
        )
        self.assertEqual(process["mcp_tools"], ["search_process_trial_cases"])
        self.assertIn("supplied by the user", process["prerequisites"][0])

    @patch("platform_core.views.collect_readiness")
    def test_demo_status_reports_service_and_dataset_readiness(self, collect_readiness) -> None:
        collect_readiness.return_value = {
            "status": "ok",
            "services": [{"name": "database", "status": "ok", "detail": None}],
        }

        response = self.client.get("/api/v1/demo/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data_scope"], "public_demo")
        self.assertEqual(body["demo_data"]["indexed_knowledge_documents"], 0)
        self.assertIn("assistant_provider", body)
