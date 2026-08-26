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

The values in `.env.example` are development placeholders. Before external access:

- replace `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`;
- set explicit allowed hosts and CORS origins;
- terminate TLS at an authenticated gateway;
- do not publish PostgreSQL, Redis, Qdrant, or Docker daemon ports;
- never commit `.env` or LLM API keys.

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
