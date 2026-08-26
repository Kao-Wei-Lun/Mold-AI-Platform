import asyncio
import json
from unittest.mock import patch

import httpx
from django.test import SimpleTestCase

from platform_core.mcp_gateway import (
    PlatformAPIClient,
    get_job_status,
    get_similarity_explanation,
    run_design_review,
)


class MCPGatewayTests(SimpleTestCase):
    def test_review_tool_maps_only_the_canonical_demo_measurement_context(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertEqual(
                payload["context"],
                {
                    "nominal_wall_thickness_mm": 2.0,
                    "max_rib_thickness_mm": 1.2,
                    "minimum_draft_angle_deg": 1.5,
                },
            )
            return httpx.Response(
                202,
                json={
                    "schema_version": "1.0",
                    "status": "accepted",
                    "review_id": "review-1",
                    "job_id": "job-1",
                },
            )

        client = PlatformAPIClient(
            "http://platform.test/api/v1",
            "https://demo.example.test",
            httpx.MockTransport(handler),
        )
        with patch("platform_core.mcp_gateway._client", return_value=client):
            result = asyncio.run(
                run_design_review(
                    "artifact-version-1",
                    nominal_wall_thickness_mm=2.0,
                    max_rib_thickness_mm=1.2,
                    minimum_draft_angle_deg=1.5,
                )
            )

        self.assertEqual(result.domain_result["job_id"], "job-1")
        self.assertIn("review-1", result.links["ui"])

    def test_job_tool_returns_canonical_result_and_absolute_deep_link(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["X-Mold-AI-Client"], "mcp-gateway")
            return httpx.Response(
                200,
                json={
                    "schema_version": "1.0",
                    "job_id": "job-1",
                    "state": "running",
                    "stage": "reranking",
                    "progress": 70,
                },
            )

        client = PlatformAPIClient(
            "http://platform.test/api/v1",
            "https://demo.example.test",
            httpx.MockTransport(handler),
        )
        with patch("platform_core.mcp_gateway._client", return_value=client):
            result = asyncio.run(get_job_status("job-1"))

        self.assertEqual(result.domain_result["state"], "running")
        self.assertEqual(result.links["ui"], "https://demo.example.test/?job_id=job-1")
        self.assertIn("70%", result.summary)

    def test_explanation_tool_returns_only_requested_candidate(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "schema_version": "1.0",
                    "search_id": "search-1",
                    "job_id": "job-1",
                    "state": "succeeded",
                    "result": {
                        "query_ref": {"artifact_name": "Query"},
                        "profile": "demo-general@1.0",
                        "index_version": "cad-demo-v1",
                        "results": [
                            {
                                "artifact_version_id": "candidate-a",
                                "artifact_name": "Reference A",
                                "rank": 1,
                                "overall_score": 0.92,
                            },
                            {
                                "artifact_version_id": "candidate-b",
                                "artifact_name": "Reference B",
                                "rank": 2,
                                "overall_score": 0.81,
                            },
                        ],
                        "limitations": [],
                        "lineage_ref": "similarity-search:search-1",
                    },
                },
            )

        client = PlatformAPIClient(
            "http://platform.test/api/v1",
            "https://demo.example.test",
            httpx.MockTransport(handler),
        )
        with patch("platform_core.mcp_gateway._client", return_value=client):
            result = asyncio.run(get_similarity_explanation("search-1", "candidate-a"))

        self.assertEqual(result.domain_result["candidate"]["artifact_name"], "Reference A")
        self.assertNotIn("results", result.domain_result)
        self.assertIn("92.0%", result.summary)
