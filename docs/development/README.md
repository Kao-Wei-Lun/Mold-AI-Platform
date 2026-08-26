# Development Guide

## Implemented stages

Stage 1 provides the runnable foundation shared by future capabilities:

- Django REST API with liveness, readiness, and safe system-info endpoints.
- Celery worker using Redis.
- PostgreSQL, Redis, and Qdrant through Docker Compose.
- Vue/TypeScript frontend that reports dependency readiness.
- Backend/frontend tests and GitHub Actions CI.

Stage 2 adds versioned STEP/STL upload, the canonical Artifact/Job/CADModel records, an isolated CAD
queue, OpenCascade/Trimesh parsing, derived preview lineage, polling APIs, and a Three.js viewer.
See [stage-02-cad-ingestion.md](stage-02-cad-ingestion.md) for its contract and known security gaps.

Stage 3 adds versioned deterministic feature extraction, scoped Qdrant indexing, asynchronous
similarity search, explainable reranking, and side-by-side comparison. See
[stage-03-cad-similarity.md](stage-03-cad-similarity.md) for the score contract and limitations.

Stage 4 adds a checksum-protected Demo rule catalog, deterministic asynchronous Design Review,
typed findings with evidence and lineage, immutable reviewer decisions, audit events, and a Web
review workspace. See [stage-04-design-review.md](stage-04-design-review.md) for evaluator and
measurement boundaries.

Stage 5 adds governed TXT/Markdown ingestion, document/chunk provenance, prompt-injection
quarantine, server-derived ACL filtering, deterministic hybrid Qdrant retrieval, clickable
citations, and explicit abstention. See [stage-05-knowledge-rag.md](stage-05-knowledge-rag.md) for
retrieval and security boundaries.

Stage 6 adds a versioned minimal UI Context envelope, deterministic context-aware similarity
explanations, a frontend UI Action allowlist, provider degradation visibility, and a separate
Streamable HTTP MCP Gateway exposing five focused Capability adapters. See
[stage-06-assistant-mcp.md](stage-06-assistant-mcp.md) for the protocol, current ChatGPT boundary,
and external-access prerequisites.

Stage 7 adds a canonical Trial → ProcessRun → Parameter / Defect / CorrectiveAction graph, an
idempotent synthetic-data Connector, explainable deterministic case ranking, compatibility
abstention, engineer-gated historical ranges, lineage/audit records, and a Process/Trial Web
workspace. See [stage-07-process-trial.md](stage-07-process-trial.md) for data, scoring, and safety
boundaries.

Stage 8 adds canonical CAE Study/Run/Result records, an idempotent synthetic structured-export
Connector, solver/material/mesh compatibility gates, compatible metric subsets, deterministic
deltas, result-level evidence, lineage/audit records, and a CAE comparison Web workspace. See
[stage-08-cae-comparison.md](stage-08-cae-comparison.md) for integration-level and comparison
boundaries.

Stage 9 adds immutable HMI source artifacts, a bounded synthetic screen profile, deterministic
numeric extraction with confidence and source regions, mandatory low-confidence human review, and
versioned reviewed-parameter XLSX exports with audit/lineage data. See
[stage-09-machine-ui-excel.md](stage-09-machine-ui-excel.md) for the fixed-profile boundary and
Enterprise replacement path.

Stage 10 adds controlled Demo bearer access, authenticated artifact delivery, security and MCP
preflight contracts, a TLS production Compose overlay, release validation scripts, and a current
official ChatGPT/Secure MCP Tunnel runbook without claiming external account or OAuth completion.
See [stage-10-demo-release-hardening.md](stage-10-demo-release-hardening.md) for deployment and
remaining operator checks.

Stage 11 adds an owner-only Sites remote console, a token-protected production Web behind a
temporary HTTPS Quick Tunnel, a separate loopback MCP port, and Windows scripts for OpenAI Secure
MCP Tunnel startup. See [stage-11-sites-tunnels.md](stage-11-sites-tunnels.md) for the private
external-test runbook and the remaining account-bound steps.

## Prerequisites

- Windows 11 with WSL2 and Docker Desktop.
- Python 3.12 for host-side tests.
- Node.js 22 and npm.
- NVIDIA GPU support is not required until the CAD/AI worker stages.

## Start the development environment

From PowerShell in the repository root:

```powershell
.\scripts\dev.ps1
```

The script copies `.env.example` to `.env` when needed, then builds and starts the Compose
services.

- Web UI: <http://localhost:5173>
- API liveness: <http://localhost:8000/api/v1/health/live>
- API readiness: <http://localhost:8000/api/v1/health/ready>
- Django admin: <http://localhost:8000/admin/>
- MCP Gateway (local preflight only): <http://localhost:8001/mcp>
- MCP Gateway liveness: <http://localhost:8001/health/live>
- Security preflight: <http://localhost:8000/api/v1/security/preflight>
- MCP preflight: <http://localhost:8001/preflight>

The database, Redis, and Qdrant ports are intentionally not published to the Windows host.

## Run tests locally

Create the backend environment once:

```powershell
cd services\platform-api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
cd ..\..
```

Install frontend dependencies once:

```powershell
cd apps\web
npm install
cd ..\..
```

Run all implemented-stage checks:

```powershell
.\scripts\test.ps1
```

Verify the running container stack, including an actual Celery task round trip:

```powershell
.\scripts\smoke.ps1
```

## Secrets and external access

The values in `.env.example` are development placeholders. For controlled external access, use
`release.env.example` and the Stage 10 runbook. Before external access:

- replace `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`;
- set explicit allowed hosts and CORS origins;
- terminate TLS at the provided Caddy gateway and enable required Demo authentication;
- do not publish PostgreSQL, Redis, Qdrant, or Docker daemon ports;
- never commit `.env` or LLM API keys.

The local MCP endpoint intentionally has no user authentication and is restricted to the approved
public Demo data scope. Do not forward it to the Internet. ChatGPT testing requires a controlled
public HTTPS endpoint or Secure MCP Tunnel plus the account/workspace and authorization preflight
described in Stages 6 and 10.

## Implemented similarity pipeline

Stage 3 builds on the parsed geometry:

```text
geometry feature extraction
-> versioned feature schema
-> Qdrant indexing
-> explainable CAD similarity search
-> side-by-side result comparison
```

## Implemented design-review pipeline

```text
parsed CADModel + RuleProfile snapshot
-> registered deterministic evaluators
-> versioned findings and evidence
-> reviewer decision history and audit event
```

## Implemented knowledge pipeline

```text
versioned public Demo document
-> scan and section/paragraph chunks
-> ACL-scoped deterministic text index
-> extractive evidence with citations or abstention
```

## Implemented Assistant and MCP adapter

```text
versioned UI references
-> server-side context resolution
-> deterministic evidence-backed fallback answer
-> validated UI Action

ChatGPT / MCP client
-> Streamable HTTP /mcp
-> focused tool schema + safety annotations
-> existing REST Capability API
```

## Implemented Process/Trial pipeline

```text
synthetic connector record + version/hash
-> canonical Trial / ProcessRun / Parameter / Defect / Action
-> deterministic multi-lane case ranking
-> compatibility and validation guardrails
-> evidence-backed controlled-trial references or abstention
```

## Implemented CAE comparison pipeline

```text
synthetic structured export + source version/hash
-> canonical CAEStudy / CAERun / CAEResult
-> run compatibility gate
-> compatible metric subset
-> deterministic delta + result-level evidence or blocked comparison
```

## Implemented Machine UI to Excel pipeline

```text
versioned HMI image + fixed Demo profile
-> bounded deterministic numeric extraction
-> confidence, units, validation, and normalized source regions
-> explicit human confirmation/correction gate
-> versioned XLSX with reviewed values and lineage
```
