# Stage 14 — OpenAI Responses Provider Operations

Stage 14 is implemented with a safe deterministic default. Normal automated tests use a fake HTTP
transport and do not call OpenAI or create API usage. A real call occurs only after an operator sets
`LLM_PROVIDER=openai`, a separate inference API key, an explicit model, and deliberately runs the
live test or uses the Web Assistant.

## Security and product boundary

- Keep `OPENAI_API_KEY` on the API server. Do not put it in Vue/Sites variables, URLs, screenshots,
  source control, MCP tool arguments, logs, or ChatGPT messages. OpenAI's API documentation says API
  keys are secrets and should be loaded server-side from an environment variable or key-management
  service: <https://platform.openai.com/docs/api-reference/authentication>.
- Create an inference key in a dedicated OpenAI Project. Do not reuse the Secure MCP Tunnel runtime
  key, an organization Admin key, `CONTROL_PLANE_API_KEY`, `MCP_BEARER_TOKEN`, or `DEMO_API_TOKEN`.
- The adapter uses the Responses API with an explicit runtime model, strict JSON Schema output and
  `store: false`. The current request contract is documented at
  <https://developers.openai.com/api/reference/cli/resources/responses/methods/create>.
- Only persisted `public_demo` evidence may cross the provider boundary. Company data requires a
  new retention, region, classification, Project and approval review.
- The model explains persisted results. It does not calculate or overwrite Similarity scores,
  Design Review decisions, Process evidence, CAE deltas, approval state, or UI URLs.

## Configuration

Keep committed examples blank. For a private PowerShell session, load the secret without printing it:

```powershell
cd C:\project\Mold-AI-Platform
$secureKey = Read-Host "Paste the separate OpenAI inference API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
Remove-Variable secureKey

$env:LLM_PROVIDER = "openai"
$env:OPENAI_MODEL = "<approved model selector>"
$env:OPENAI_ALLOWED_MODELS = $env:OPENAI_MODEL
$env:OPENAI_PROVIDER_PROFILE = "openai-demo-public-v1"
$env:OPENAI_PROMPT_PROFILE = "mold-assistant-grounded-v1"
```

There is intentionally no hidden model default. Before choosing a model, verify its current
Responses API and Structured Outputs support on the official model page and verify the Project's
limits and budget. The OpenAI quickstart documents environment-based key loading and Responses API
usage: <https://platform.openai.com/docs/quickstart>.

Optional bounded settings:

```text
OPENAI_TIMEOUT_SECONDS=20
OPENAI_MAX_OUTPUT_TOKENS=1200
OPENAI_MAX_INPUT_CHARS=24000
OPENAI_MAX_CONCURRENCY=2
```

The base URL is restricted to `https://api.openai.com/v1` in this Demo profile. Enterprise gateways
or other providers require a separate reviewed adapter/profile instead of silently redirecting this
one.

## Start or refresh the private Sites Demo

The Sites overlay explicitly passes only the Stage 14 variables to the API container. If the values
are in the current PowerShell environment, recreate only the API service:

```powershell
docker compose --env-file .env.sites-demo -f compose.yaml -f compose.sites-demo.yaml `
  up -d --build --force-recreate api
```

Check configuration health without creating model usage:

```powershell
$headers = @{ Authorization = "Bearer <current Demo access token>" }
Invoke-RestMethod -Headers $headers `
  -Uri "https://<current-quick-tunnel>/api/v1/assistant/capabilities"
```

Expected configured state: `provider=openai-responses`, `mode=openai`, `status=ok`, and
`llm_available=true`. This is a configuration check, not proof that a real inference succeeded.

## Test gates

Free default tests:

```powershell
cd C:\project\Mold-AI-Platform\services\platform-api
.\.venv\Scripts\python.exe -m pytest platform_core/tests/test_assistant_providers.py `
  platform_core/tests/test_assistant.py
```

Potentially billable live UAT — run only after confirming the Project, budget and approved model:

```powershell
$env:RUN_OPENAI_LIVE_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest `
  platform_core/tests/test_openai_live.py -q
Remove-Item Env:RUN_OPENAI_LIVE_TESTS
```

The live test sends one small synthetic public evidence envelope. It does not send CAD files,
company data, tokens, or tunnel settings. A successful result must contain the expected evidence
reference, required limitation and API-reported token usage.

## Failure and rollback

401, 429, timeout, 5xx, refusal, malformed output, schema mismatch, unknown evidence reference,
missing limitation and unsupported new numeric values all produce a typed reason and preserve the
deterministic engineering answer. They do not turn the Assistant endpoint into an HTTP 500.

To stop further provider calls without changing any domain data:

```powershell
$env:LLM_PROVIDER = "deterministic-demo"
docker compose --env-file .env.sites-demo -f compose.yaml -f compose.sites-demo.yaml `
  up -d --force-recreate api
```

Stopping the browser's wait does not prove that an already-sent provider request was cancelled and
may not prevent API usage. The Web UI states this explicitly.
