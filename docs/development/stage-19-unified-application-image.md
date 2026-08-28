# Stage 19: Unified production application image

## Outcome

The Release and Sites Demo profiles build one versioned application image:

```text
mold-ai-platform-app:<APP_VERSION>
```

The API, Engineering Web, MCP Gateway, general worker and CAD worker run as separate containers
from that same immutable image. PostgreSQL, Redis, Qdrant, Cloudflare Tunnel and the Release Caddy
gateway remain independent vendor images because they have separate lifecycle, persistence and
security responsibilities.

## Image construction

The repository-root `Dockerfile` uses two stages:

1. `web-build` installs the locked Node dependencies and creates the Vue production bundle.
2. `production` installs the Python runtime and Nginx, copies the Platform API/MCP/worker code,
   then copies the compiled Web bundle from the first stage.

Node.js, source `node_modules` and frontend build caches are not present in the final image. The
final image runs as the unprivileged `app` user. Nginx listens on port 8080 and uses `/tmp` for its
PID and temporary request/proxy files so Web does not require a root container.

## Runtime roles

| Compose service | Command in the unified image | Responsibility |
| --- | --- | --- |
| `api` | `scripts/start-api-*.sh` | migrations, preflight and Gunicorn API |
| `web` | `nginx -g ...` | SPA assets, security headers and `/api/` reverse proxy |
| `mcp-gateway` | `python -m platform_core.mcp_gateway` | Streamable HTTP MCP surface |
| `worker` | `celery ... --queues=general` | general asynchronous jobs |
| `worker-cad` | `celery ... --queues=cad` | isolated CAD processing jobs |

Keeping these processes in separate containers preserves health checks, restart policy, queue
isolation and future independent scaling while removing duplicate application image tags.

## Build and verification

Sites Demo:

```powershell
docker compose -f compose.yaml -f compose.sites-demo.yaml --env-file .env.sites-demo build
docker compose -f compose.yaml -f compose.sites-demo.yaml --env-file .env.sites-demo up -d
docker compose -f compose.yaml -f compose.sites-demo.yaml --env-file .env.sites-demo config --images
.\scripts\sites-demo-smoke.ps1
```

Release:

```powershell
docker compose -f compose.yaml -f compose.release.yaml --env-file release.env up -d --build
```

`scripts/test.ps1` renders both production Compose profiles and fails unless all five application
services resolve to exactly one `mold-ai-platform-app` image.

## Operational notes

- Set `APP_VERSION` to a new immutable release identifier before production rollout.
- Rebuilding the shared image recreates all five application containers; persistent data remains
  in the named PostgreSQL, Redis, Qdrant and artifact volumes.
- Do not combine the five runtime commands into one container process. A shared image is the
  deployment optimization; separate containers remain the reliability boundary.
- Old service-specific images may be removed only after every running container has switched to
  the unified image and the external smoke gate passes.
