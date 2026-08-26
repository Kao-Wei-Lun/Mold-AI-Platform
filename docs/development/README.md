# Development Guide

## Stage 1 scope

This stage provides the runnable foundation shared by future CAD, similarity, review, RAG,
assistant, and MCP capabilities:

- Django REST API with liveness, readiness, and safe system-info endpoints.
- Celery worker using Redis.
- PostgreSQL, Redis, and Qdrant through Docker Compose.
- Vue/TypeScript frontend that reports dependency readiness.
- Backend/frontend tests and GitHub Actions CI.

CAD processing, business data models, authentication, and AI functionality intentionally begin
in later stages after this foundation is verified.

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

Run all Stage 1 checks:

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

## Next stage

Stage 2 implements the first vertical slice:

```text
STEP/STL upload
-> immutable ArtifactVersion
-> asynchronous Job
-> isolated CAD Worker
-> geometry metadata and preview artifact
-> frontend job status and result view
```
