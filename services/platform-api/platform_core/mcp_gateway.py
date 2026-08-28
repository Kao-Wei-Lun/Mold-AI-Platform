from __future__ import annotations

import os
import secrets
import uuid
from typing import Any, Literal

import httpx
import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .deep_links import DeepLinkBuilder, deep_link_readiness


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return "change_me" in lowered or "change-me" in lowered


def _configured_secret(value: str) -> bool:
    return len(value) >= 32 and not _is_placeholder(value)


class ToolResponse(BaseModel):
    schema_version: str = "1.0"
    summary: str
    domain_result: dict[str, Any]
    links: dict[str, str] = Field(default_factory=dict)


class PlatformAPIError(RuntimeError):
    pass


class PlatformAPIClient:
    def __init__(
        self,
        base_url: str | None = None,
        public_web_entry_base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        api_token: str | None = None,
        forwarded_proto: str | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("PLATFORM_API_BASE_URL", "http://api:8000/api/v1")
        ).rstrip("/")
        self.public_web_entry_base_url = (
            public_web_entry_base_url
            or os.getenv("PUBLIC_WEB_ENTRY_BASE_URL")
            or os.getenv("PUBLIC_WEB_BASE_URL", "http://localhost:5173")
        ).rstrip("/")
        self.transport = transport
        self.api_token = api_token if api_token is not None else os.getenv("PLATFORM_API_TOKEN", "")
        self.forwarded_proto = (
            forwarded_proto
            if forwarded_proto is not None
            else os.getenv("PLATFORM_API_FORWARDED_PROTO", "")
        )

    async def request(
        self, method: str, path: str, *, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(15.0, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
            try:
                headers = {"Accept": "application/json", "X-Mold-AI-Client": "mcp-gateway"}
                if self.api_token:
                    headers["Authorization"] = f"Bearer {self.api_token}"
                if self.forwarded_proto:
                    headers["X-Forwarded-Proto"] = self.forwarded_proto
                response = await client.request(
                    method,
                    f"{self.base_url}/{path.lstrip('/')}",
                    json=payload,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                raise PlatformAPIError("The Mold AI capability API is unavailable.") from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise PlatformAPIError(
                "The Mold AI capability API returned an invalid response."
            ) from exc
        if response.is_error:
            error = body.get("error", {}) if isinstance(body, dict) else {}
            message = error.get("message") or error.get("code") or f"HTTP {response.status_code}"
            raise PlatformAPIError(str(message))
        if not isinstance(body, dict):
            raise PlatformAPIError("The Mold AI capability API returned an invalid response.")
        return body

    def deep_link(self, target: str, **refs: str | None) -> str:
        allow_local = self.public_web_entry_base_url.startswith("http://localhost")
        return DeepLinkBuilder(
            self.public_web_entry_base_url,
            allow_local=allow_local,
        ).build(target, **refs)


def _client() -> PlatformAPIClient:
    return PlatformAPIClient()


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
CREATE_ANALYSIS_JOB = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

mcp = MCPServer(
    name="mold-ai-platform",
    title="Mold AI Platform",
    description="Governed public-demo mold engineering capabilities.",
    version="0.2.0",
    instructions=(
        "When the user asks to use Mold AI Platform, prefer these MCP tools over Browser or Web UI "
        "automation. Use focused read tools for evidence and status. Never invent required "
        "engineering inputs, silently substitute UI defaults, or switch from Knowledge retrieval "
        "to Process/Trial evidence without telling the user. Search and review tools may persist "
        "analysis records; call get_job_status before claiming asynchronous work is complete. "
        "All exposed data is public synthetic Demo data."
    ),
)


@mcp.tool(
    name="list_engineering_capabilities",
    title="List Mold AI engineering capabilities",
    description=(
        "Use this when the user asks what Mold AI Platform can do. Return the canonical Demo "
        "capability catalog, prerequisites, limitations, and the MCP tools actually available."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
async def list_engineering_capabilities() -> ToolResponse:
    client = _client()
    result = await client.request("GET", "engineering-capabilities")
    capabilities = result.get("capabilities", [])
    mcp_count = sum(len(item.get("mcp_tools", [])) for item in capabilities)
    return ToolResponse(
        summary=(
            f"Mold AI Platform reports {len(capabilities)} Demo engineering capabilities "
            f"with {mcp_count} capability-to-tool mappings."
        ),
        domain_result=result,
        links={"ui": client.deep_link("home")},
    )


@mcp.tool(
    name="get_platform_status",
    title="Get Mold AI Demo platform status",
    description=(
        "Use this when the user asks whether Mold AI Platform services or Demo datasets are ready. "
        "Return current dependency status, indexed knowledge count, fixture counts, and Assistant "
        "provider state."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
async def get_platform_status() -> ToolResponse:
    client = _client()
    result = await client.request("GET", "demo/status")
    demo_data = result.get("demo_data", {})
    return ToolResponse(
        summary=(
            f"Mold AI Demo is {result.get('status', 'unknown')}; "
            f"{demo_data.get('indexed_knowledge_documents', 0)} indexed knowledge documents and "
            f"{demo_data.get('process_trial_cases', 0)} process/trial cases are available."
        ),
        domain_result={
            **result,
            "deep_links": deep_link_readiness(client.public_web_entry_base_url),
        },
        links={"ui": client.deep_link("home")},
    )


@mcp.tool(
    name="search_similar_molds",
    title="Search similar molds",
    description=(
        "Create an asynchronous similarity-search job for an already processed CAD artifact "
        "version. Use get_job_status with the returned job_id before discussing results."
    ),
    annotations=CREATE_ANALYSIS_JOB,
    structured_output=True,
)
async def search_similar_molds(
    cad_artifact_version_id: str,
    top_k: int = 5,
    dataset_ids: list[str] | None = None,
    product_types: list[str] | None = None,
    material_codes: list[str] | None = None,
) -> ToolResponse:
    client = _client()
    result = await client.request(
        "POST",
        "similarity-searches",
        payload={
            "schema_version": "1.0",
            "idempotency_key": f"mcp-sim-{uuid.uuid4()}",
            "query": {"cad_artifact_version_id": cad_artifact_version_id},
            "filters": {
                "dataset_ids": dataset_ids or ["curated-cad-demo-v1"],
                "product_types": product_types or [],
                "material_codes": material_codes or [],
            },
            "top_k": top_k,
        },
    )
    links = {
        "job": client.deep_link("job", job_id=result["job_id"]),
        "result": client.deep_link("similarity", search_id=result["search_id"]),
    }
    return ToolResponse(
        summary=f"Similarity search accepted as job {result['job_id']}.",
        domain_result=result,
        links=links,
    )


@mcp.tool(
    name="get_similarity_explanation",
    title="Explain a similarity result",
    description=(
        "Explain one candidate from a completed similarity search using persisted lane scores, "
        "differences, limitations, and evidence references."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
async def get_similarity_explanation(
    search_id: str, candidate_artifact_version_id: str
) -> ToolResponse:
    client = _client()
    search = await client.request("GET", f"similarity-searches/{search_id}")
    if search.get("state") != "succeeded" or not search.get("result"):
        return ToolResponse(
            summary=f"Similarity search {search_id} is {search.get('state', 'not ready')}.",
            domain_result={
                "schema_version": "1.0",
                "search_id": search_id,
                "job_id": search.get("job_id"),
                "state": search.get("state"),
                "candidate": None,
            },
            links={"job": client.deep_link("job", job_id=search.get("job_id"))},
        )
    result = search["result"]
    candidate = next(
        (
            item
            for item in result.get("results", [])
            if item.get("artifact_version_id") == candidate_artifact_version_id
        ),
        None,
    )
    if candidate is None:
        raise PlatformAPIError("The candidate is not part of this similarity search.")
    explanation = {
        "schema_version": "1.0",
        "search_id": search_id,
        "job_id": search.get("job_id"),
        "query_ref": result.get("query_ref"),
        "profile": result.get("profile"),
        "index_version": result.get("index_version"),
        "candidate": candidate,
        "limitations": result.get("limitations", []),
        "lineage_ref": result.get("lineage_ref"),
    }
    return ToolResponse(
        summary=(
            f"{candidate.get('artifact_name', 'Candidate')} ranked #{candidate.get('rank')} "
            f"with overall score {float(candidate.get('overall_score', 0)) * 100:.1f}%."
        ),
        domain_result=explanation,
        links={
            "ui": client.deep_link(
                "similarity",
                search_id=search_id,
                candidate_id=candidate_artifact_version_id,
            )
        },
    )


@mcp.tool(
    name="run_design_review",
    title="Run a design review",
    description=(
        "Create an asynchronous deterministic design-rule review for an already processed CAD "
        "artifact version. This does not approve, waive, or modify engineering findings."
    ),
    annotations=CREATE_ANALYSIS_JOB,
    structured_output=True,
)
async def run_design_review(
    cad_artifact_version_id: str,
    nominal_wall_thickness_mm: float | None = None,
    max_rib_thickness_mm: float | None = None,
    minimum_draft_angle_deg: float | None = None,
) -> ToolResponse:
    client = _client()
    context: dict[str, Any] = {}
    if nominal_wall_thickness_mm is not None:
        context["nominal_wall_thickness_mm"] = nominal_wall_thickness_mm
    if max_rib_thickness_mm is not None:
        context["max_rib_thickness_mm"] = max_rib_thickness_mm
    if minimum_draft_angle_deg is not None:
        context["minimum_draft_angle_deg"] = minimum_draft_angle_deg
    result = await client.request(
        "POST",
        "design-reviews",
        payload={
            "schema_version": "1.0",
            "cad_artifact_version_id": cad_artifact_version_id,
            "idempotency_key": f"mcp-review-{uuid.uuid4()}",
            "context": context,
        },
    )
    return ToolResponse(
        summary=f"Design review accepted as job {result['job_id']}.",
        domain_result=result,
        links={"ui": client.deep_link("design_review", review_id=result["review_id"])},
    )


@mcp.tool(
    name="get_job_status",
    title="Get an engineering job status",
    description="Read the current state, progress, typed error, and result of a Mold AI job.",
    annotations=READ_ONLY,
    structured_output=True,
)
async def get_job_status(job_id: str) -> ToolResponse:
    client = _client()
    result = await client.request("GET", f"jobs/{job_id}")
    return ToolResponse(
        summary=(
            f"Job {job_id} is {result.get('state')} at {result.get('progress')}% "
            f"({result.get('stage')})."
        ),
        domain_result=result,
        links={"ui": client.deep_link("job", job_id=job_id)},
    )


@mcp.tool(
    name="search_knowledge",
    title="Search governed mold knowledge",
    description=(
        "Search authorized public-demo mold knowledge and return extractive claims with source "
        "citations. The tool abstains when evidence is insufficient."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
async def search_knowledge(
    query: str,
    top_k: int = 5,
    document_types: list[str] | None = None,
    authority_levels: list[str] | None = None,
) -> ToolResponse:
    client = _client()
    result = await client.request(
        "POST",
        "knowledge-searches",
        payload={
            "query": query,
            "top_k": top_k,
            "document_types": document_types or [],
            "authority_levels": authority_levels or [],
            "dataset_ids": ["public-knowledge-demo-v1"],
        },
    )
    summary = (
        "The knowledge search abstained because authorized evidence was insufficient."
        if result.get("abstained")
        else f"Found {len(result.get('results', []))} governed evidence passages."
    )
    return ToolResponse(
        summary=summary,
        domain_result=result,
        links={"ui": client.deep_link("knowledge", knowledge_search_id=result["search_id"])},
    )


@mcp.tool(
    name="list_knowledge_documents",
    title="List indexed Mold AI knowledge documents",
    description=(
        "Use this before or after Knowledge retrieval when the user asks what governed source "
        "documents are available. Return public Demo document metadata and ingestion status; do "
        "not substitute Process/Trial cases for missing documents."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
async def list_knowledge_documents() -> ToolResponse:
    client = _client()
    result = await client.request("GET", "knowledge-documents")
    items = [
        item
        for item in result.get("items", [])
        if item.get("dataset_id") == "public-knowledge-demo-v1"
    ]
    indexed = [item for item in items if item.get("ingestion_status") == "indexed"]
    domain_result = {**result, "items": items, "indexed_count": len(indexed)}
    return ToolResponse(
        summary=f"Found {len(indexed)} indexed public Demo knowledge documents.",
        domain_result=domain_result,
        links={"ui": client.deep_link("home")},
    )


@mcp.tool(
    name="search_process_trial_cases",
    title="Search synthetic process and trial cases",
    description=(
        "Use this only when the user asks for Process/Trial case evidence and supplies both a "
        "defect code and material code. Do not call it as an automatic replacement for an empty "
        "Knowledge search, and do not invent machine, product, location, or process parameters. "
        "Results are synthetic historical evidence and never machine-setting instructions."
    ),
    annotations=READ_ONLY,
    structured_output=True,
)
async def search_process_trial_cases(
    defect_code: str,
    material_code: str,
    machine_code: str | None = None,
    product_type: str | None = None,
    location: str | None = None,
    injection_pressure_mpa: float | None = None,
    injection_speed_mm_s: float | None = None,
    melt_temperature_c: float | None = None,
    top_k: int = 5,
    input_source: Literal["user_provided", "explicit_demo_fixture"] = "user_provided",
) -> ToolResponse:
    client = _client()
    parameters: dict[str, dict[str, float | str]] = {}
    if injection_pressure_mpa is not None:
        parameters["injection_pressure_mpa"] = {"value": injection_pressure_mpa, "unit": "MPa"}
    if injection_speed_mm_s is not None:
        parameters["injection_speed_mm_s"] = {"value": injection_speed_mm_s, "unit": "mm/s"}
    if melt_temperature_c is not None:
        parameters["melt_temperature_c"] = {"value": melt_temperature_c, "unit": "degC"}
    payload: dict[str, object] = {
        "defect_code": defect_code,
        "material_code": material_code,
        "parameters": parameters,
        "top_k": top_k,
    }
    for key, value in {
        "machine_code": machine_code,
        "product_type": product_type,
        "location": location,
    }.items():
        if value:
            payload[key] = value
    result = await client.request("POST", "process-case-searches", payload=payload)
    domain_result = {
        **result,
        "input_provenance": {
            "source": input_source,
            "demo_defaults_used": input_source == "explicit_demo_fixture",
            "omitted_optional_inputs": [
                key
                for key, value in {
                    "machine_code": machine_code,
                    "product_type": product_type,
                    "location": location,
                    "injection_pressure_mpa": injection_pressure_mpa,
                    "injection_speed_mm_s": injection_speed_mm_s,
                    "melt_temperature_c": melt_temperature_c,
                }.items()
                if value is None
            ],
        },
    }
    result_count = int(result.get("result_count", len(result.get("results", []))))
    return ToolResponse(
        summary=(
            f"Found {result_count} compatible synthetic Process/Trial cases. "
            f"Input source: {input_source}."
        ),
        domain_result=domain_result,
        links={"ui": client.deep_link("process_trial", process_search_id=result["search_id"])},
    )


async def health(_: Request) -> JSONResponse:
    auth_mode = os.getenv("MCP_AUTH_MODE", "none").lower()
    return JSONResponse(
        {
            "status": "ok",
            "service": "mcp-gateway",
            "transport": "streamable-http",
            "endpoint": "/mcp",
            "data_scope": "public-demo",
            "authentication": auth_mode,
        }
    )


def mcp_preflight_payload() -> dict[str, object]:
    auth_mode = os.getenv("MCP_AUTH_MODE", "none").lower()
    bearer_token = os.getenv("MCP_BEARER_TOKEN", "")
    bearer_configured = _configured_secret(bearer_token)
    api_auth_required = os.getenv("DEMO_AUTH_MODE", "disabled").lower() in {
        "required",
        "local",
    }
    platform_api_token_configured = _configured_secret(os.getenv("PLATFORM_API_TOKEN", ""))
    public_base_url = os.getenv("PUBLIC_MCP_BASE_URL", "")
    tunnel_id = os.getenv("SECURE_MCP_TUNNEL_ID", "")
    entry_base_url = os.getenv("PUBLIC_WEB_ENTRY_BASE_URL", "")
    deep_links = deep_link_readiness(entry_base_url)
    public_https = public_base_url.startswith("https://")
    tunnel_configured = bool(tunnel_id) and not _is_placeholder(tunnel_id)
    mode_valid = auth_mode in {"none", "bearer", "oauth"}
    oauth_implemented = False
    connection_path = (
        "secure_mcp_tunnel"
        if tunnel_configured
        else ("public_https" if public_https else "local_only")
    )
    chatgpt_ready = (
        tunnel_configured
        and auth_mode == "none"
        and (not api_auth_required or platform_api_token_configured)
        and bool(deep_links["ready"])
    )
    return {
        "schema_version": "1.0",
        "service": "mcp-gateway",
        "transport": "streamable-http",
        "endpoint": "/mcp",
        "tool_count": 9,
        "data_scope": "public-demo",
        "authentication": {
            "mode": auth_mode,
            "mode_valid": mode_valid,
            "bearer_configured": bearer_configured,
            "oauth_implemented": oauth_implemented,
            "platform_api_token_configured": platform_api_token_configured,
        },
        "connection": {
            "path": connection_path,
            "public_https_configured": public_https,
            "secure_tunnel_configured": tunnel_configured,
        },
        "deep_links": deep_links,
        "server_side_chatgpt_preflight_ready": chatgpt_ready,
        "openai_account_workspace_validation": "pending_external_check",
        "inspector_ready": auth_mode == "none" or (auth_mode == "bearer" and bearer_configured),
        "limitations": [
            "Bearer mode is for controlled MCP Inspector or custom-client testing only.",
            "Public ChatGPT user authentication requires OAuth 2.1 and is not implemented.",
            "Tunnel readiness still depends on OpenAI organization and workspace association.",
        ],
    }


async def preflight(_: Request) -> JSONResponse:
    return JSONResponse(mcp_preflight_payload())


class MCPAccessMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in {"/mcp", "/mcp/"}:
            await self.app(scope, receive, send)
            return

        auth_mode = os.getenv("MCP_AUTH_MODE", "none").lower()
        if auth_mode == "none":
            await self.app(scope, receive, send)
            return
        if auth_mode == "oauth":
            await self._error(
                scope,
                receive,
                send,
                "MCP_OAUTH_NOT_IMPLEMENTED",
                "OAuth mode is not available until an approved identity provider is configured.",
                503,
            )
            return
        configured_token = os.getenv("MCP_BEARER_TOKEN", "")
        if auth_mode != "bearer" or not _configured_secret(configured_token):
            await self._error(
                scope,
                receive,
                send,
                "MCP_AUTH_CONFIGURATION_ERROR",
                "MCP authentication is misconfigured.",
                503,
            )
            return

        headers = {key.decode().lower(): value.decode() for key, value in scope.get("headers", [])}
        authorization = headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if (
            not separator
            or scheme.lower() != "bearer"
            or not secrets.compare_digest(token, configured_token)
        ):
            await self._error(
                scope,
                receive,
                send,
                "MCP_AUTH_TOKEN_INVALID",
                "A valid MCP bearer token is required.",
                401,
                authenticate=True,
            )
            return
        await self.app(scope, receive, send)

    @staticmethod
    async def _error(
        scope: Scope,
        receive: Receive,
        send: Send,
        code: str,
        message: str,
        status: int,
        *,
        authenticate: bool = False,
    ) -> None:
        response = JSONResponse(
            {"error": {"code": code, "message": message, "retryable": False}},
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )
        if authenticate:
            response.headers["WWW-Authenticate"] = 'Bearer realm="mold-ai-mcp"'
        await response(scope, receive, send)


def create_app():
    allowed_hosts = [
        value.strip()
        for value in os.getenv("MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*,mcp-gateway:*").split(
            ","
        )
        if value.strip()
    ]
    allowed_origins = [
        value.strip()
        for value in os.getenv("MCP_ALLOWED_ORIGINS", "http://localhost:*").split(",")
        if value.strip()
    ]
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        host="0.0.0.0",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        ),
    )
    app.routes.append(Route("/health/live", health, methods=["GET"]))
    app.routes.append(Route("/preflight", preflight, methods=["GET"]))
    return MCPAccessMiddleware(app)


def main() -> None:
    uvicorn.run(
        create_app(),
        host=os.getenv("MCP_BIND_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8001")),
        log_level=os.getenv("MCP_LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
