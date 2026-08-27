"""Canonical public-demo capability catalog shared by REST and MCP adapters."""

from __future__ import annotations

CAPABILITIES: tuple[dict[str, object], ...] = (
    {
        "capability_id": "cad.ingest",
        "title": "CAD import and processing",
        "status": "demo_ready",
        "web_available": True,
        "mcp_tools": [],
        "prerequisites": ["STEP or STL upload"],
        "limitations": ["CAD upload is currently available through the Engineering Web UI."],
    },
    {
        "capability_id": "mold.similarity_search",
        "title": "CAD geometry similarity search",
        "status": "demo_ready",
        "web_available": True,
        "mcp_tools": ["search_similar_molds", "get_similarity_explanation"],
        "prerequisites": ["Processed and indexed CAD artifact version"],
        "limitations": ["Public synthetic Demo dataset only."],
    },
    {
        "capability_id": "design.review",
        "title": "Deterministic design review",
        "status": "demo_ready",
        "web_available": True,
        "mcp_tools": ["run_design_review", "get_job_status"],
        "prerequisites": ["Processed CAD artifact version"],
        "limitations": ["Demo rules do not approve or waive engineering findings."],
    },
    {
        "capability_id": "knowledge.retrieve",
        "title": "Governed engineering knowledge retrieval",
        "status": "demo_ready",
        "web_available": True,
        "mcp_tools": ["list_knowledge_documents", "search_knowledge"],
        "prerequisites": ["Indexed public Demo knowledge documents"],
        "limitations": ["Extractive evidence only; no LLM synthesis."],
    },
    {
        "capability_id": "process.case_search",
        "title": "Process and trial case comparison",
        "status": "demo_ready",
        "web_available": True,
        "mcp_tools": ["search_process_trial_cases"],
        "prerequisites": ["Defect code and material code supplied by the user"],
        "limitations": [
            "Synthetic evidence only; never writes MES, PLC, or molding-machine settings."
        ],
    },
    {
        "capability_id": "cae.compare",
        "title": "CAE and Moldflow result comparison",
        "status": "demo_ready",
        "web_available": True,
        "mcp_tools": [],
        "prerequisites": ["Compatible structured Demo studies"],
        "limitations": ["Synthetic exports; no official solver API connection."],
    },
    {
        "capability_id": "hmi.extract_export",
        "title": "Machine HMI extraction and Excel export",
        "status": "demo_ready",
        "web_available": True,
        "mcp_tools": [],
        "prerequisites": ["PNG or JPG image and human review"],
        "limitations": ["Web workflow only; extraction never writes machine settings."],
    },
    {
        "capability_id": "assistant.explain",
        "title": "Embedded Mold AI Assistant",
        "status": "safe_fallback",
        "web_available": True,
        "mcp_tools": [],
        "prerequisites": ["Supported UI context"],
        "limitations": ["Current Demo uses deterministic explanations when LLM is disabled."],
    },
)


def engineering_capabilities_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "data_scope": "public_demo",
        "capabilities": [dict(capability) for capability in CAPABILITIES],
    }
