# Stage 12 — MCP grounding and governed Demo data

## Why this stage was added

A live ChatGPT test exposed four integration gaps: ChatGPT could fall back to Browser instead of
the named Mold AI MCP connection, it could not ask the platform what was implemented or ready,
the public Knowledge dataset did not contain the requested Traditional Chinese short-shot
evidence, and the Process/Trial Web form silently supplied Demo values. Those behaviors made a
plausible response possible without proving which platform capability or inputs produced it.

Stage 12 corrects the platform contracts. It does not claim that MCP instructions can force every
ChatGPT routing decision; the operator must still select the Mold AI connection and confirm that a
tool call appears in the conversation.

## Delivered behavior

### Canonical discovery and status

The REST API now exposes:

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/engineering-capabilities` | Eight implemented capability records with status, prerequisites, limitations, Web availability, and actual MCP mappings |
| `GET /api/v1/demo/status` | Dependency readiness, public fixture counts, Assistant provider health, version, and environment |

The MCP Gateway exposes nine focused tools:

1. `list_engineering_capabilities`
2. `get_platform_status`
3. `search_similar_molds`
4. `get_similarity_explanation`
5. `run_design_review`
6. `get_job_status`
7. `list_knowledge_documents`
8. `search_knowledge`
9. `search_process_trial_cases`

Tool descriptions and server instructions state the routing and grounding boundaries: use Mold AI
tools when the user names the platform, do not invent required engineering inputs, do not silently
replace Knowledge with Process/Trial evidence, and do not claim asynchronous completion before
checking the job.

### Governed Demo Knowledge

`python manage.py seed_demo_data` idempotently loads the approved public fixtures for Knowledge,
Process/Trial, and CAE. The Knowledge fixture is a Traditional Chinese short-shot troubleshooting
guide that explicitly separates historical evidence from proven causation and forbids automatic
machine writes or guessed process values.

Knowledge datasets are now separated:

| Dataset | Visibility and use |
|---|---|
| `public-knowledge-demo-v1` | User-visible governed Demo documents and all MCP Knowledge calls |
| `automated-smoke-v1` | Test-only documents created by `scripts/smoke.ps1` |

Both the database candidate query and Qdrant filter enforce this dataset boundary. Traditional
Chinese retrieval adds CJK bigrams to the existing deterministic feature hashing so phrases such as
`射出成型短射` retain lexical support. It remains an extractive Demo retriever, not a learned
semantic embedding or causal engineering model.

### Explicit Process/Trial inputs

The Web query starts empty. Search remains disabled until the operator supplies defect and material.
The button **Use explicit Demo inputs** deliberately fills the synthetic fixture values. The MCP
tool likewise requires defect and material, omits optional fields that were not supplied, and
returns `input_provenance.source` as either `user_provided` or `explicit_demo_fixture`.

No path writes MES, PLC, or molding-machine settings.

## Startup and migration behavior

`scripts/sites-demo-start.ps1` waits for the API and executes `seed_demo_data` before reporting the
external Demo as ready. `scripts/smoke.ps1` does the same and writes its temporary Knowledge source
only to `automated-smoke-v1`. The seed command also relabels legacy artifacts named
`Stage 5 smoke knowledge guide` from the public Knowledge dataset to the automated-smoke dataset.

The operation is idempotent: rerunning startup does not duplicate approved fixtures.

## ChatGPT retest

After rebuilding and restarting the stack and Secure MCP Tunnel:

1. Open the Mold AI developer-mode connection and refresh its tool metadata.
2. Start a new conversation and explicitly select **Mold AI Platform** from the tools menu.
3. Ask “請使用 Mold AI Platform 列出目前能力與 Demo 狀態。” Confirm that
   `list_engineering_capabilities` and `get_platform_status` appear as tool calls.
4. Ask “請使用 Mold AI Platform 的 Knowledge 查詢射出成型短射。” Confirm a governed citation
   from `射出成型短射 Demo 排查指南`; Browser should not be the evidence source.
5. Ask for Process/Trial evidence without a material code. The client should request the missing
   value rather than inventing one. Then provide `PA6-GF30` and confirm the returned input
   provenance is `user_provided`.
6. If ChatGPT still invokes Browser, record the selected connection, visible tool call trace,
   prompt, time, and workspace. That is client routing evidence, not a server data failure.

Current OpenAI documentation recommends focused tools with clear descriptions and schemas and
requires testing the connected plugin/tool metadata in ChatGPT developer mode. The application
must be refreshed after tool metadata changes:

- [Plan your tools](https://developers.openai.com/plugins/plan/tools)
- [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)

## Verification

```powershell
.\scripts\test.ps1
docker compose up -d --build
.\scripts\smoke.ps1
```

Automated coverage includes canonical discovery/status, nine-tool MCP discovery, MCP REST adapter
payloads, public-versus-smoke Knowledge isolation, Traditional Chinese lexical retrieval,
idempotent fixture seeding, explicit Process input provenance, and the empty-by-default Web form.
