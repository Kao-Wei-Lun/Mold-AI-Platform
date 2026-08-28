# Stage 18: External local identity and ChatGPT Plugin UI

Stage 18 replaces the shared browser Demo token with personal Mold AI sessions and adds the
ChatGPT-to-Web launcher experience specified in
[`requirements/14_External_Sites_Identity_MCP_Plugin_UI_SRS.md`](../requirements/14_External_Sites_Identity_MCP_Plugin_UI_SRS.md).

## Runtime identity split

- Browser users authenticate in Engineering Web with a local Mold AI account. Django owns the
  HttpOnly session and CSRF boundary.
- The owner-only Sites portal stores only the current `https://*.trycloudflare.com` origin in
  `sessionStorage`.
- MCP Gateway calls Platform API with `MCP_PLATFORM_SERVICE_TOKEN` and
  `X-Mold-AI-Client: mcp-gateway`. This service principal has only public-demo read/write scope.
- The old `DEMO_API_TOKEN` remains an empty compatibility setting in Sites mode and is never
  transferred to the browser.

## First start or upgrade

```powershell
cd C:\project\Mold-AI-Platform
.\scripts\sites-demo-start.ps1
```

The start script upgrades the private `.env.sites-demo` to `DEMO_AUTH_MODE=local`, creates a
random MCP service credential when missing, rebuilds the services, and prints the current Quick
Tunnel origin. It never prints the service credential.

If no Platform Admin exists, keep the containers running and execute the one-time interactive
bootstrap. The command accepts no password argument and does not store a default password:

```powershell
docker compose -f compose.yaml -f compose.sites-demo.yaml --env-file .env.sites-demo exec api `
  python manage.py bootstrap_local_admin --username <your-name>
```

Then rerun the start script or external smoke:

```powershell
.\scripts\sites-demo-smoke.ps1
.\scripts\sites-demo-status.ps1
```

In Sites, paste only the Quick Tunnel origin. Engineering Web then presents the personal login.

## Rotation

Rotate the internal service credential and recreate affected containers:

```powershell
.\scripts\sites-demo-start.ps1 -RotateServiceCredential
```

Do not paste this credential into Sites, ChatGPT, a URL, a screenshot, an issue, or a Git file.

## ChatGPT second experience

The `open_mold_ai_web` MCP tool returns a server-built stable Sites deep link and associates it
with `ui://mold-ai/open-web-v1.html`. In a compatible ChatGPT Plugin UI host, the card uses the
official `openExternal` capability after a user click. The tool still returns a normal summary
and link to MCP clients that do not render UI.

After rebuilding MCP Gateway, refresh the **Mold AI Platform** connection in ChatGPT so the
updated tool/resource metadata is discovered. Actual card rendering and external-open behavior
remain an account/workspace UAT step.
