# Stage 10 — Demo Release Hardening

## Outcome

This stage makes the single-machine Demo defensible for controlled external use. It adds a
session-only Demo access token, fail-closed API/MCP middleware, non-secret readiness documents,
authenticated artifact downloads, a TLS production topology, and operator preflight scripts.

It does **not** claim Enterprise identity, completed ChatGPT workspace access, a live Secure MCP
Tunnel, or OAuth. Those require external configuration and validation.

## Deployment topology

```text
external browser
  -> Caddy :443 (automatic TLS)
  -> Nginx :8080 (SPA + /api reverse proxy)
  -> Django/Gunicorn :8000

ChatGPT developer-mode app
  -> OpenAI-hosted Secure MCP Tunnel endpoint
  <- outbound HTTPS from tunnel-client on Windows
  -> 127.0.0.1:8001/mcp
  -> MCP Gateway
  -> Django Capability APIs
```

Only Caddy publishes the Web/API service. PostgreSQL, Redis, Qdrant, and Django do not publish
host ports in the release overlay. MCP remains bound to Windows loopback for the tunnel client.

## Authentication boundary

### Web and REST Demo

- `DEMO_AUTH_MODE=required` protects every `/api/v1/*` endpoint except liveness, readiness, and
  the security preflight.
- The user enters a controlled Demo bearer token in the UI. It is kept only in `sessionStorage`,
  never compiled into the Web bundle.
- Read and write scopes are checked separately. Denials have typed error codes, correlation IDs,
  safe audit records, `no-store`, and no token contents.
- CAD previews, knowledge citations, and XLSX exports use authenticated fetch/Blob downloads;
  direct browser links cannot bypass the access middleware.

This is appropriate only for a small, controlled Demo audience. Enterprise replaces it with SSO,
short-lived user tokens, RBAC/ABAC, revocation, rate limiting, and centralized audit/SIEM.

### MCP Demo

Recommended mode is `MCP_AUTH_MODE=none` while `/mcp` is reachable only on loopback and through
Secure MCP Tunnel. OpenAI documents the tunnel as an outbound-only path that keeps the private MCP
server off the public Internet; it also states that tunnel permissions and ChatGPT developer-mode
workspace access are separate checks. See the official
[Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

`MCP_AUTH_MODE=bearer` is available only for MCP Inspector or another custom client. A static token
is not represented as ChatGPT OAuth. For an authenticated public MCP server, OpenAI expects OAuth
2.1, authorization-code + PKCE S256, protected resource/auth-server metadata, token validation,
audience/scope enforcement, and a real identity provider. See
[Authentication for plugins](https://developers.openai.com/plugins/build/auth).

## Release configuration

1. Copy `release.env.example` to the ignored file `release.env`.
2. Replace every `CHANGE_ME` value with a randomly generated secret, correct public domain, email,
   and real tunnel ID.
3. Point public DNS A/AAAA records to the Windows host and allow inbound TCP 80/443 plus UDP 443 if
   HTTP/3 is desired. Do not open 8000, 8001, 5173, 5432, 6379, or 6333.
4. Validate before starting:

```powershell
.\scripts\release-preflight.ps1
```

5. Start the release overlay:

```powershell
docker compose -f compose.yaml -f compose.release.yaml --env-file release.env up -d --build
```

The API container runs migrations and `deployment_preflight --strict` before Gunicorn. A
placeholder, weak token, development secret, wildcard/missing public allowed host, non-HTTPS CORS,
missing secure proxy/cookie/HSTS settings, or absent MCP connection mode prevents API startup.

6. Validate the external path from a different network:

```powershell
.\scripts\release-smoke.ps1 -BaseUrl "https://mold.example.com" -DemoToken "<demo-token>"
```

The script confirms HTTPS Web access, a 401 without the token, and successful API access with the
token. It never prints the token.

## ChatGPT and Secure MCP Tunnel runbook

Current OpenAI documentation says developer-mode MCP testing requires a public HTTPS Streamable
HTTP endpoint (normally `/mcp`) or Secure MCP Tunnel, and that developer mode availability may
depend on the account/workspace policy. MCP Inspector should first validate discovery, schemas,
annotations, auth errors, and representative calls. See
[Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt).

Server-side checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health/live
Invoke-RestMethod http://127.0.0.1:8001/preflight
docker compose exec -T api python scripts/mcp_smoke.py
npx @modelcontextprotocol/inspector@latest
```

External checks that cannot be automated by this repository:

1. In Platform tunnel settings, create a tunnel and associate both the intended Platform
   organization and target ChatGPT workspace.
2. Confirm the operator has Tunnels Read + Use; creation/editing additionally needs Manage.
3. Download the current `tunnel-client` from Platform settings or the latest official release.
   Do not hard-code a release URL.
4. Set the runtime key only in the process environment, never in Git:

```powershell
$env:CONTROL_PLANE_API_KEY = "<runtime-key>"
tunnel-client help quickstart
tunnel-client init --sample sample_mcp_stdio_local --profile mold-ai-demo --tunnel-id <tunnel-id> --mcp-server-url http://127.0.0.1:8001/mcp
tunnel-client doctor --profile mold-ai-demo --explain
tunnel-client run --profile mold-ai-demo
```

The HTTP flag follows the official guidance to replace the sample's stdio command with
`--mcp-server-url`. Keep `run` healthy during discovery and calls.

5. In ChatGPT Settings → Security and login, enable Developer mode if the account/workspace permits
   it. Create a developer-mode app, select **Tunnel**, choose the associated tunnel, inspect the
   nine discovered tools, then run positive, follow-up, negative, missing-ID, and empty-result test
   prompts.
6. Record the ChatGPT workspace, operator, tunnel ID, tested tool schema version, results, and date
   in the release evidence. Until these checks pass, `/preflight` intentionally reports
   `openai_account_workspace_validation=pending_external_check`.

Secure MCP Tunnel is for private connections and developer-mode testing; OpenAI states it does not
replace the stable public HTTPS endpoint required for public plugin submission/distribution. The
Demo does not claim public marketplace publication.

## Public MCP alternative

Do not expose the current loopback MCP endpoint directly. A future public MCP deployment needs:

- a separate public HTTPS hostname and Streamable HTTP `/mcp` route;
- an established OAuth 2.1/OIDC provider and standards-compliant discovery;
- PKCE S256 and supported client registration;
- signature, issuer, audience, expiry, replay, and scope checks on every bearer token;
- rate limiting, WAF/abuse controls, security monitoring, data minimization, privacy policy, and
  review evidence.

The current `MCP_AUTH_MODE=oauth` deliberately returns `MCP_OAUTH_NOT_IMPLEMENTED`; it never falls
back to anonymous behavior.

## Verification contract

- Backend tests cover missing/invalid token denial, scopes, safe audit events, request IDs,
  placeholder/weak configuration, release readiness, MCP bearer behavior, API-token forwarding,
  and truthful MCP preflight.
- Frontend tests cover token connection/disconnection, 401 handling, authorization headers, and
  protected Blob downloads.
- `scripts/test.ps1` covers lint, formatting, Django checks, migration drift, all unit/component
  tests, Web production build, and Compose validation.
- `scripts/smoke.ps1` covers the local development boundary and confirms that neither security nor
  MCP preflight overstates production/ChatGPT readiness.

## Known limitations

- One shared Demo token has no per-human attribution or revocation list.
- No request rate limiter/WAF is included on the single Windows host.
- Caddy certificate issuance requires correct public DNS and inbound network reachability.
- Tunnel creation, runtime key, ChatGPT developer mode, workspace association, and permissions are
  external prerequisites and remain unverified until an operator completes the runbook.
- Enterprise OAuth/SSO and public plugin submission are future stages.
