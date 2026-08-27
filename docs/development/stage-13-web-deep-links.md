# Stage 13 — Stable ChatGPT-to-Web Deep Links

## Outcome

Stage 13 replaces the non-routable `dynamic-quick-tunnel.invalid` MCP links with a versioned,
token-safe route through the stable owner-only Sites portal:

```text
ChatGPT MCP tool result
  -> https://mold-ai-remote-demo.weilunkao1013.chatgpt.site/open?...safe refs...
  -> authenticated Sites dispatcher
  -> current https://*.trycloudflare.com Engineering Web
  -> API GET by canonical UUID
```

The Quick Tunnel may change after a container restart. MCP metadata and the ChatGPT connection do
not need to change because every MCP link continues to point to the stable Sites origin.

## Deep Link Contract 1.0

Every link contains `deep_link_version=1.0`, one allowlisted `target`, and only the identifiers
defined for that target. Identifiers are canonical lowercase UUIDs.

| Target | Required reference | Optional reference |
|---|---|---|
| `home` | — | — |
| `job` | `job_id` | — |
| `similarity` | `search_id` | `candidate_id` |
| `design_review` | `review_id` | `finding_id` |
| `knowledge` | `knowledge_search_id` | `citation_id` |
| `process_trial` | `process_search_id` | `case_id` |
| `cae` | `cae_comparison_id` | `metric_code` |
| `hmi` | `hmi_extraction_id` | — |

Tokens, keys, Tunnel IDs, arbitrary return URLs, permission claims and serialized domain results
are rejected. The Demo bearer token stays in Sites `sessionStorage`, crosses to Engineering Web in
the URL fragment, and is removed from browser history immediately after consumption.

## Configuration

The ignored `.env.sites-demo` must contain the stable Sites origin:

```dotenv
PUBLIC_WEB_ENTRY_BASE_URL=https://mold-ai-remote-demo.weilunkao1013.chatgpt.site
```

`sites-demo-start.ps1` rejects HTTP, localhost, credential-bearing, path-bearing and `.invalid`
entry URLs. The production-like API allows browser CORS only from this configured Sites origin.
Local development retains an explicit `http://localhost:5173` exception; this exception never
passes the external Demo deep-link readiness gate.

## Operator flow

```powershell
cd C:\project\Mold-AI-Platform
.\scripts\sites-demo-start.ps1
.\scripts\sites-demo-smoke.ps1
.\scripts\sites-demo-status.ps1
```

When ChatGPT returns a link:

1. Open it while signed in to the owner account for the private Site.
2. Confirm or replace the current Quick Tunnel URL and Demo token.
3. Select **驗證連線**. Sites performs an authenticated `system/info` identity check.
4. Select **開啟指定內容**.
5. Engineering Web reloads the record with GET and selects the requested child evidence only when
   it belongs to the referenced parent result.

An invalid version, target, UUID, duplicate field, unexpected field or cross-parent child is
rejected. A deep link never creates a new search, review, decision or machine action.

## Validation

Automated coverage includes:

- Python DeepLinkBuilder origin, schema, UUID and sensitive-field rejection tests.
- MCP tool contract tests for stable `/open` links and preflight readiness.
- Sites parser security cases, authenticated identity check, lint and Vinext production build.
- Engineering Web parser security cases, safe observability metadata and GET-only resolution tests.
- Web typecheck, component suite and Vite production build.
- Compose expansion plus external Web/API/MCP smoke checks.

The final account-bound acceptance is performed from the ChatGPT App after the updated Sites
version and MCP Gateway containers are running. Test `get_platform_status`, `get_job_status`,
`get_similarity_explanation`, `search_knowledge` and `search_process_trial_cases`, then open every
returned link and confirm the expected module and selected record.

## Rollback

If the dispatcher is unavailable, MCP domain results remain valid. The operator may use the Sites
home page and manually open the Workspace. Never roll back to `.invalid`, a dynamic Tunnel URL in
MCP metadata, or a URL containing the Demo token.
