import asyncio
import json
import os
from unittest.mock import patch

import httpx
from django.test import SimpleTestCase

from platform_core.mcp_gateway import (
    MCPAccessMiddleware,
    PlatformAPIClient,
    create_app,
    get_job_status,
    get_platform_status,
    get_similarity_explanation,
    list_engineering_capabilities,
    list_knowledge_documents,
    run_design_review,
    search_process_trial_cases,
)


class MCPGatewayTests(SimpleTestCase):
    def test_capability_and_status_tools_return_canonical_rest_results(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/engineering-capabilities"):
                return httpx.Response(
                    200,
                    json={
                        "schema_version": "1.0",
                        "capabilities": [
                            {
                                "capability_id": "knowledge.retrieve",
                                "mcp_tools": ["search_knowledge", "list_knowledge_documents"],
                            }
                        ],
                    },
                )
            if request.url.path.endswith("/demo/status"):
                return httpx.Response(
                    200,
                    json={
                        "schema_version": "1.0",
                        "status": "ok",
                        "demo_data": {
                            "indexed_knowledge_documents": 1,
                            "process_trial_cases": 6,
                        },
                    },
                )
            raise AssertionError(f"Unexpected request: {request.url}")

        client = PlatformAPIClient(
            "http://platform.test/api/v1",
            "https://demo.example.test",
            httpx.MockTransport(handler),
        )
        with patch("platform_core.mcp_gateway._client", return_value=client):
            capabilities = asyncio.run(list_engineering_capabilities())
            platform_status = asyncio.run(get_platform_status())

        self.assertEqual(
            capabilities.domain_result["capabilities"][0]["capability_id"],
            "knowledge.retrieve",
        )
        self.assertIn("1 Demo engineering capabilities", capabilities.summary)
        self.assertIn("6 process/trial cases", platform_status.summary)

    def test_knowledge_catalog_excludes_automated_smoke_documents(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "schema_version": "1.0",
                    "items": [
                        {
                            "document_id": "demo-1",
                            "dataset_id": "public-knowledge-demo-v1",
                            "ingestion_status": "indexed",
                        },
                        {
                            "document_id": "smoke-1",
                            "dataset_id": "automated-smoke-v1",
                            "ingestion_status": "indexed",
                        },
                    ],
                },
            )

        client = PlatformAPIClient(
            "http://platform.test/api/v1",
            "https://demo.example.test",
            httpx.MockTransport(handler),
        )
        with patch("platform_core.mcp_gateway._client", return_value=client):
            result = asyncio.run(list_knowledge_documents())

        self.assertEqual(result.domain_result["indexed_count"], 1)
        self.assertEqual(result.domain_result["items"][0]["document_id"], "demo-1")

    def test_process_tool_omits_unprovided_defaults_and_reports_input_source(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertEqual(
                payload,
                {
                    "defect_code": "short_shot",
                    "material_code": "PA6-GF30",
                    "parameters": {},
                    "top_k": 3,
                },
            )
            return httpx.Response(
                200,
                json={
                    "schema_version": "1.0",
                    "search_id": "process-search-1",
                    "result_count": 2,
                    "results": [],
                },
            )

        client = PlatformAPIClient(
            "http://platform.test/api/v1",
            "https://demo.example.test",
            httpx.MockTransport(handler),
        )
        with patch("platform_core.mcp_gateway._client", return_value=client):
            result = asyncio.run(search_process_trial_cases("short_shot", "PA6-GF30", top_k=3))

        provenance = result.domain_result["input_provenance"]
        self.assertEqual(provenance["source"], "user_provided")
        self.assertFalse(provenance["demo_defaults_used"])
        self.assertIn("machine_code", provenance["omitted_optional_inputs"])

    def test_platform_client_forwards_only_configured_internal_bearer_token(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["Authorization"], "Bearer internal-demo-token")
            return httpx.Response(200, json={"schema_version": "1.0", "status": "ok"})

        client = PlatformAPIClient(
            "http://platform.test/api/v1",
            "https://demo.example.test",
            httpx.MockTransport(handler),
            "internal-demo-token",
        )
        result = asyncio.run(client.request("GET", "system/info"))

        self.assertEqual(result["status"], "ok")

    def test_platform_client_can_mark_a_trusted_internal_request_as_https(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["X-Forwarded-Proto"], "https")
            return httpx.Response(200, json={"schema_version": "1.0", "status": "ok"})

        client = PlatformAPIClient(
            "http://platform.test/api/v1",
            "https://demo.example.test",
            httpx.MockTransport(handler),
            forwarded_proto="https",
        )

        result = asyncio.run(client.request("GET", "system/info"))

        self.assertEqual(result["status"], "ok")

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

    def test_mcp_bearer_mode_fails_closed_but_leaves_preflight_public(self) -> None:
        token = "mcp-stage10-token-0123456789abcdef"

        async def exercise() -> None:
            async def downstream(scope, receive, send) -> None:
                await send({"type": "http.response.start", "status": 204, "headers": []})
                await send({"type": "http.response.body", "body": b""})

            with patch.dict(
                os.environ,
                {
                    "MCP_AUTH_MODE": "bearer",
                    "MCP_BEARER_TOKEN": token,
                    "MCP_ALLOWED_HOSTS": "testserver:*",
                    "MCP_ALLOWED_ORIGINS": "http://testserver:*",
                },
                clear=False,
            ):
                transport = httpx.ASGITransport(app=create_app())
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://testserver"
                ) as client:
                    preflight = await client.get("/preflight")
                guarded_transport = httpx.ASGITransport(app=MCPAccessMiddleware(downstream))
                async with httpx.AsyncClient(
                    transport=guarded_transport, base_url="http://testserver"
                ) as client:
                    denied = await client.post("/mcp", json={})
                    accepted_by_auth = await client.post(
                        "/mcp", json={}, headers={"Authorization": f"Bearer {token}"}
                    )

            self.assertEqual(preflight.status_code, 200)
            self.assertTrue(preflight.json()["inspector_ready"])
            self.assertFalse(preflight.json()["server_side_chatgpt_preflight_ready"])
            self.assertEqual(denied.status_code, 401)
            self.assertEqual(denied.json()["error"]["code"], "MCP_AUTH_TOKEN_INVALID")
            self.assertIn("Bearer", denied.headers["WWW-Authenticate"])
            self.assertNotEqual(accepted_by_auth.status_code, 401)

        asyncio.run(exercise())

    def test_tunnel_preflight_does_not_claim_account_or_workspace_validation(self) -> None:
        async def exercise() -> dict:
            with patch.dict(
                os.environ,
                {
                    "MCP_AUTH_MODE": "none",
                    "SECURE_MCP_TUNNEL_ID": "tunnel_example",
                    "PUBLIC_MCP_BASE_URL": "",
                    "MCP_ALLOWED_HOSTS": "testserver:*",
                },
                clear=False,
            ):
                transport = httpx.ASGITransport(app=create_app())
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://testserver"
                ) as client:
                    return (await client.get("/preflight")).json()

        payload = asyncio.run(exercise())
        self.assertEqual(payload["connection"]["path"], "secure_mcp_tunnel")
        self.assertTrue(payload["server_side_chatgpt_preflight_ready"])
        self.assertEqual(payload["openai_account_workspace_validation"], "pending_external_check")
        self.assertIn("depends on OpenAI", " ".join(payload["limitations"]))
