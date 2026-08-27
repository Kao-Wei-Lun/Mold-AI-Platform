# Stage 6 — Context-aware Assistant and MCP Gateway

## Delivered scope

Stage 6 adds two adapters over the existing engineering capabilities:

```text
Engineering Web UI
-> Context Envelope 1.0 (references only)
-> Assistant API
-> server-side context resolution
-> deterministic evidence-backed answer
-> UI Action Protocol 1.0 allowlist

MCP client
-> Streamable HTTP /mcp
-> MCP Gateway
-> existing REST Capability APIs
-> canonical result + concise summary + absolute UI deep link
```

The Assistant and MCP Gateway never replace CAD parsing, similarity scoring, deterministic rule
evaluation, job state, or Knowledge retrieval. They explain or coordinate those persisted results.

## Embedded Assistant contract

The browser sends only versioned UI references: page, selected artifact/search/candidate/job IDs,
and locale. Unknown fields, unsupported context versions/pages, and malformed UUIDs are rejected.
The backend reloads each selected record; client-supplied object metadata or permission claims are
not trusted.

The first supported contextual intent is “why did this candidate rank first?” The response separates
summary, facts, interpretation, recommendations, uncertainty/limitations, and evidence references.
It also records a hashed `assistant.message_processed.v1` audit event.

The browser accepts only `assistant.show_evidence` in UI Action Protocol 1.0. It validates protocol
version, expiry, page precondition, search ID, and candidate ID before selecting and scrolling to the
persisted evidence. Arbitrary URLs, selectors, JavaScript, approval, waiver, and destructive actions
are not executable.

## Provider abstraction and degradation

`LLMProvider` and provider-health contracts are provider neutral. Stage 6 intentionally ships only a
`deterministic-demo` fallback: no prompt or engineering data is sent to an external LLM. The UI
explicitly reports `degraded / safe fallback`; CAD, Similarity, Review, and Knowledge remain usable.

An OpenAI, Anthropic, local, or company adapter can later implement the same boundary. Selecting a
provider name in the environment does not make it available until its adapter, data policy, model
capability profile, regression evaluation, timeouts, and secret handling are implemented.

## MCP tool catalog

The separate `mcp-gateway` service exposes Streamable HTTP at `/mcp`. It does not connect to the
database; every tool calls the versioned REST API.

| Tool | State change | Behavior |
|---|---:|---|
| `search_similar_molds` | Create analysis job | Returns `search_id` and `job_id` immediately |
| `get_similarity_explanation` | No | Returns only the requested candidate and its evidence |
| `run_design_review` | Create analysis job | Returns `review_id` and `job_id` immediately |
| `get_job_status` | No | Returns canonical job progress/error/result |
| `search_knowledge` | No domain write | Returns authorized extractive evidence or abstention |
| `list_engineering_capabilities` | No | Returns the canonical implemented capability catalog |
| `get_platform_status` | No | Returns live service, Demo data, and Assistant readiness |
| `list_knowledge_documents` | No | Lists governed public Demo Knowledge documents |
| `search_process_trial_cases` | No domain write | Searches synthetic cases from explicit user inputs |

Every tool has an explicit input schema, output schema, focused description, and accurate
`readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint` annotations. Results include
structured canonical data, a model-readable summary, and an absolute Engineering UI deep link.

Run protocol discovery and a real tool call against the local stack:

```powershell
docker compose exec -T api python scripts/mcp_smoke.py
```

## Current ChatGPT and external-access boundary

The implementation follows the OpenAI documentation checked on 2026-08-26:

- OpenAI currently recommends focused MCP tools that work without custom UI and supports the
  official TypeScript or Python MCP SDKs with Streamable HTTP.
- ChatGPT developer testing requires a public HTTPS MCP endpoint or Secure MCP Tunnel. Developer
  Mode availability can depend on account and workspace policy.
- Safety annotations guide client behavior but never replace server authorization, validation, or
  confirmation.

Official references:

- [Build an MCP server](https://developers.openai.com/plugins/build/mcp-server)
- [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [MCP and Connectors](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)

The current `http://localhost:8001/mcp` endpoint is a local protocol preflight only. It has no user
authentication and may access only approved public Demo data. Do not expose it directly to the
Internet. Before a ChatGPT demo, add a controlled HTTPS endpoint or Secure MCP Tunnel, verify the
specific account/workspace capability, and implement the intended authentication flow. Private data
or user actions require OAuth/OIDC-compatible authorization and per-tool server-side policy.

## Verification

```powershell
.\scripts\test.ps1
.\scripts\smoke.ps1
```

Stage 6 tests cover context minimization/validation, contextual explanation, audit creation,
provider degradation, UI Action expiry/target/allowlist checks, MCP REST adapter behavior, MCP
initialization, nine-tool discovery, tool schemas/annotations, and actual status/Knowledge calls.
The four catalog/status/process tools were added in Stage 12 without changing the REST-adapter
boundary.
