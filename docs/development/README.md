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
Streamable HTTP MCP Gateway initially exposing five focused Capability adapters. See
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

Stage 12 adds a canonical capability catalog and live Demo status, expands the MCP Gateway to nine
focused tools, seeds governed Traditional Chinese troubleshooting evidence, isolates automated
smoke documents, and removes silent Process/Trial defaults. See
[stage-12-mcp-grounding-demo-data.md](stage-12-mcp-grounding-demo-data.md) for the observed ChatGPT
failure modes, corrected contracts, and retest procedure.

Stage 13 adds a versioned Deep Link Contract, a stable owner-only Sites `/open` dispatcher,
authenticated Workspace identity verification, GET-only record resumption, parent-child evidence
validation, and explicit MCP deep-link readiness. See
[stage-13-web-deep-links.md](stage-13-web-deep-links.md) for configuration, operator flow and
ChatGPT acceptance steps.

Stage 14 adds an environment-selected OpenAI Responses adapter, versioned public-demo evidence
envelopes, strict Structured Outputs validation, typed failure fallback, usage/request metadata,
five grounded engineering explanation lanes, and truthful Web provider states. See
[stage-14-openai-provider.md](stage-14-openai-provider.md) for key separation, configuration, free
fake tests and the opt-in potentially billable live UAT.

## Planned stages to Demo v1.0

The detailed implementation backlog is maintained in the
[Demo v1.0 Completion Plan](../planning/demo-v1/00_README.md):

- Stage 13: implemented; stable, token-safe ChatGPT-to-Web deep links (external ChatGPT UAT after deployment).
- Stage 14: implementation complete; account-bound OpenAI live UAT remains for Stage 16 evidence.
- Stage 15: implementation complete; the isolated curated CAD corpus, manifest/checksums,
  provenance, Golden scenarios, idempotent seed/verification and Web query picker are available.
  Running-stack release evidence remains in Stage 16.
- Stage 16 Phase A: unified start/status/stop, sanitized release snapshot/evidence, PostgreSQL plus
  artifact backup, isolated restore drill, forced Qdrant rebuild and confirmed operations reset are
  implemented. External/manual and final release gates remain Phase B.
- Stage 16 Phase C: canonical dataset reset, isolated full-volume clean-room rebuild, and automated
  Qdrant/CAD-worker recovery drills are implemented with explicit scope and confirmation gates.
- Stage 16: unified start/status/reset/backup/stop, security evidence, external UAT, and the `1.0.0-demo` release gate.
- Stage 17 Phase A: route-based Engineering Web App Shell, Guided Demo and governed read-only Mold
  Rule catalog are implemented. Workflow-level refinement and rule authoring remain later phases.
- Stage 17 Phase B: application-wide English/Traditional Chinese switching, browser preference,
  accessibility language metadata and Assistant locale propagation are implemented. Governed source
  records remain in their authored language.
- Stage 17 Phase C: controlled engineering inputs, the shared accessible FormField contract,
  required/range guidance and actionable workspace empty states are implemented. Toasts, progress
  polish and table readability remain Phase 3 follow-up work.
- Stage 17 Phase D: bounded accessible notifications, consistent busy actions and plain-language
  operation labels are implemented. The visual-system and data-readability pass follows in Phase E.
- Stage 17 Phase E: the precision-manufacturing visual system, route icons, layered workspace
  surfaces, responsive polish and more readable governed data tables are implemented.

Stages 13–16 complete the functional Demo contract. Stage 17 follows after that contract is stable
so visual and interaction changes do not obscure backend, data, security, or release regressions.

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

Demo startup and smoke verification run `python manage.py seed_demo_data` idempotently. This loads
the approved public Knowledge, Process/Trial, and CAE fixtures without mixing automated smoke-test
documents into user-visible Knowledge results.

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
-> versioned public-demo evidence envelope
-> optional validated OpenAI generation or deterministic fallback
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

## Implemented Demo operations and recovery

```text
service/dependency + Celery worker + dataset + external/MCP readiness
-> explicit core/external/optional status
-> dry-run stale-job inspection
-> confirmed requeue or typed terminal failure
-> audited recovery evidence
-> bounded HTTP/concurrency/queue performance baseline
```

## Implemented local identity foundation

Stage 18 Phase 1A adds individual local Demo accounts, secure Django sessions, CSRF enforcement,
governed roles and data scopes, account lifecycle/session revocation, identity Audit and a one-time
administrator bootstrap while preserving the legacy controlled bearer mode. See
[`stage-18-phase-1a-identity-foundation.md`](stage-18-phase-1a-identity-foundation.md).

Stage 18 Phase 1B connects those local sessions to the Engineering Web with session restoration,
individual sign-in/sign-out, account and role context, credentialed requests and automatic CSRF
protection while retaining the existing disabled and bearer modes. See
[`stage-18-phase-1b-web-account-session.md`](stage-18-phase-1b-web-account-session.md).

Stage 18 Phase 1C adds the permission-gated Accounts & access workspace for governed account
creation and profile updates, scoped role assignment/revocation, lifecycle actions, session
revocation, direct-route session restoration and self-lockout protection. See
[`stage-18-phase-1c-identity-management-ui.md`](stage-18-phase-1c-identity-management-ui.md).

Stage 18 Phase 2 adds seven governed master-data domains, bilingual lifecycle management,
optimistic locking, reference summaries and API-driven engineering choices while preserving the
single external Demo deployment. See
[`stage-18-phase-2-governed-master-data.md`](stage-18-phase-2-governed-master-data.md).

Stage 18 Phases 1D–1E replace the shared Sites browser token with local-account sessions,
isolate the MCP-to-Platform service identity, and add the ChatGPT Plugin UI external-open
experience. See
[`stage-18-external-identity-plugin-ui.md`](stage-18-external-identity-plugin-ui.md).

## Unified production application image

Stage 19 packages the compiled Engineering Web, Platform API, MCP Gateway and both worker runtimes
into one versioned production application image while retaining separate containers for each
runtime role. See
[`stage-19-unified-application-image.md`](stage-19-unified-application-image.md).

## Implemented governed data lifecycles

Stage 19 Phase 3 introduces the Project → Product Part → Mold → Revision → Artifact registry. See
[`stage-19-phase-3-mold-registry.md`](stage-19-phase-3-mold-registry.md).

Stage 20 Phase 4 adds versioned Mold Rule and Knowledge publishing, separation of duties and
immutable published history. See
[`stage-20-phase-4-rule-knowledge-lifecycle.md`](stage-20-phase-4-rule-knowledge-lifecycle.md).

Stage 21 Phase 5 adds Trial close/reopen/correction, canonical Mapping Backlog, structured CAE
import/archive and versioned HMI profile/correction management in one external Demo UI. See
[`stage-21-phase-5-engineering-data-lifecycle.md`](stage-21-phase-5-engineering-data-lifecycle.md).

Stage 23 separates quick CAD analysis from governed archiving. Exploratory uploads no longer
require a MoldRevision, while formal history continues to enforce one and both intents remain
traceable in the API and Job snapshot. See
[`stage-23-cad-upload-governance-modes.md`](stage-23-cad-upload-governance-modes.md).
