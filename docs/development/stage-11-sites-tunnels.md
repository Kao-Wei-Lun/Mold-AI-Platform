# Stage 11 — Private Sites portal, HTTPS Quick Tunnel, and ChatGPT MCP

## Outcome

This stage provides two separate outbound-only paths for a controlled personal Demo:

1. A private OpenAI Sites portal opens the complete Mold AI engineering Web through a temporary Cloudflare HTTPS Quick Tunnel.
2. ChatGPT connects to the loopback-only MCP gateway through OpenAI Secure MCP Tunnel.

Neither path requires a fixed public IP or an inbound router/firewall rule. They are testing paths, not the Enterprise production topology.

Private Sites production URL: <https://mold-ai-remote-demo.weilunkao1013.chatgpt.site>

## Security boundary

- Sites is deployed owner-only. Do not change its access policy to public for this Demo.
- The HTTPS Tunnel exposes the production Nginx Web, never the Vite development server or Django directly.
- Every non-public API route requires a generated 256-bit Demo bearer token.
- The Sites portal keeps the temporary URL and token in `sessionStorage`; the full Web consumes the token from a URL fragment and immediately removes that fragment from the address bar.
- The MCP gateway remains bound to `127.0.0.1` on host port `8002`. Secure MCP Tunnel initiates outbound HTTPS to OpenAI.
- `.env.sites-demo`, runtime URLs, API keys, and tunnel-client profiles must never be committed.

## Start the external Web Demo

Prerequisites: Docker Desktop is running and outbound HTTPS/DNS is allowed.

```powershell
cd C:\project\Mold-AI-Platform
.\scripts\sites-demo-start.ps1
```

On first start, the script creates the ignored `.env.sites-demo` with independent random PostgreSQL, Django, and Demo bearer secrets. It builds production containers, waits for health, discovers the random `https://*.trycloudflare.com` URL, and verifies the protected API through that public URL.

Paste the displayed HTTPS URL and Demo token into the private Sites portal. Select **檢查連線**, then **開啟完整工作區**. The newly opened Web validates the transferred token before rendering engineering modules.

Useful commands:

```powershell
.\scripts\sites-demo-status.ps1
.\scripts\sites-demo-status.ps1 -ShowToken
.\scripts\sites-demo-smoke.ps1
.\scripts\sites-demo-stop.ps1
```

The stop command retains Docker volumes. A Quick Tunnel URL changes whenever the `web-tunnel` container is recreated; rerun the start script and update the Sites form.

## Connect ChatGPT through Secure MCP Tunnel

The following account-bound items cannot be generated or committed by this repository:

1. In OpenAI Platform tunnel settings, create a tunnel and associate it with the Platform organization and the ChatGPT workspace/personal workspace used for the test.
2. Confirm the operator has **Tunnels Read + Use**; creating/editing also needs **Read + Manage**.
3. Install the current official `tunnel-client` with the checksum-verifying project script:

   ```powershell
   .\scripts\install-tunnel-client.ps1
   ```

   The script resolves the latest release from the official `openai/tunnel-client` repository, verifies `SHA256SUMS.txt`, and installs only into ignored `.runtime/tools`.
4. Create a runtime API key for `tunnel-client`. Do not place it in `.env.sites-demo` or Git.

For the current PowerShell session only:

```powershell
$env:OPENAI_TUNNEL_ID = "tunnel_..."
$env:CONTROL_PLANE_API_KEY = "sk-..."
.\scripts\mcp-secure-tunnel.ps1 -Initialize
```

On later runs, use the same profile without reinitializing:

```powershell
.\scripts\mcp-secure-tunnel.ps1
```

Keep that terminal running. The script first checks the local MCP preflight, runs `tunnel-client doctor --explain`, and only then starts the persistent connection.

In ChatGPT:

1. Open **Settings → Security and login** and enable Developer mode if the account/workspace permits it.
2. Open ChatGPT Plugins, select **+**, provide the Mold AI name and description, and choose **Tunnel** under Connection.
3. Select the associated tunnel or enter its exact `tunnel_id`, create the connection, and review discovered tools.
4. Start a new conversation, add the MCP connection from the tools menu, then test read-only tools before write/confirmation scenarios.

If the tunnel is not listed, check the ChatGPT workspace association, Tunnels Read + Use permission, and the still-running `tunnel-client` process. The local endpoint is `http://127.0.0.1:8002/mcp` and must never be entered as a public ChatGPT URL.

## Validation matrix

| Boundary | Automated evidence |
|---|---|
| Sites source | lint, unit tests, production vinext build, HTTP 200 preview |
| External Web | HTTPS Web 200 and live health 200 |
| API access | anonymous protected request 401; valid token request 200 |
| Browser hardening | HSTS, CSP, clickjacking and content-type headers |
| MCP server | local `/preflight` plus protocol-level MCP smoke |
| Secure MCP transport | `tunnel-client doctor` and ChatGPT tool discovery; requires the account-bound tunnel ID/key |

## Known testing limits

- Cloudflare Quick Tunnels are development/testing infrastructure: the hostname is random, there is no SLA, concurrent requests are limited, and SSE is not supported.
- The current Sites portal verifies reachability with a browser `no-cors` request; the full Web performs the authoritative token validation.
- Secure MCP Tunnel is for private developer-mode testing. Public plugin distribution requires the separate stable public endpoint/authentication review path.
- Static Demo bearer auth is deliberately not Enterprise SSO. Do not load confidential company data into this public-network Demo topology.
