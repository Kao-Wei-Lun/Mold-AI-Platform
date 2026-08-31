# Stage 31 — Mold Planning workspace and Demo release

Stage 31 implements the complete Phase 0–6 scope in
`docs/requirements/16_Mold_Planning_Workspace_Improvement_Plan.md`. It separates engineering mold
planning from rule governance and replaces the former rule-profile-first interaction with a
context-first, traceable planning workflow.

## Delivered engineering workflow

The Engineering Web now exposes `/engineering/mold-planning` as a dedicated workspace:

1. choose a governed Mold Revision and optional processed CAD version;
2. confirm canonical Product Type, Material, Mold Type, Molding Process, Project and Location
   context while retaining each value's source;
3. preview the server-side deterministic Rule Profile resolution;
4. inspect the selected standard, fallback/conflict state, reason and eligible candidates;
5. compare two or three candidates using the server-provided engineering contract;
6. save a governed Mold Plan and immutable Resolution/Requirement snapshot;
7. complete, reopen or archive the plan with optimistic concurrency;
8. hand off the exact saved resolution to Design Review, CAD, Similarity or CAE.

The governance route remains responsible for authoring, validation, approval, publication,
versioning and stopping publication. The Engineering route never edits a published rule.

## Persistence and reproducibility

The canonical persistence model consists of:

- `MoldPlan` for the scoped planning record and lifecycle;
- `MoldPlanContext` for canonical values, provenance and confirmation;
- immutable `MoldPlanResolution` revisions with context, candidate and checksum snapshots;
- immutable `MoldPlanRequirement` rows pinned to exact Rule Versions;
- `MoldPlanHandoff` contracts linking the saved resolution to downstream work.

PostgreSQL mutations lock only the `MoldPlan` row. Nullable Project, Part and CAD joins remain
read context and are deliberately excluded from `SELECT FOR UPDATE`, preserving concurrency
control without invoking PostgreSQL's nullable-outer-join lock restriction.

Publishing a new Rule Profile cannot rewrite an earlier plan. A Design Review created from a plan
verifies the pinned ruleset checksum and exposes the source Mold Plan in its detail response.

## Authorization, audit and AI boundaries

- planning read/create/manage/complete permissions are evaluated server-side;
- the MCP service identity receives only planning/registry/rule read permissions in addition to
  its bounded public Demo transport scopes; it does not receive planning create/manage/complete or
  rule override permissions;
- manual selection requires `rules:override`, an eligible published candidate and a 10–512
  character reason;
- common credential markers are rejected before an override reason can enter Audit history;
- all lifecycle, resolution, override and handoff events retain actor and target references;
- the Assistant uses the current Mold Plan and Resolution IDs but cannot publish rules or bypass
  permissions;
- MCP exposes three additional read-only planning tools, bringing the canonical Demo contract to
  13 tools.

## Golden Demo scenario

Run `scripts/demo-mold-planning-acceptance.ps1` against the active Sites Demo. The script executes
isolated backend contract scenarios and then verifies the running external surface without storing
URLs or credentials in evidence:

1. create, resolve, reopen and archive a governed plan;
2. reproduce deterministic candidate selection and immutable requirements;
3. reject unauthorized/ineligible/sensitive manual overrides;
4. create a checksum-pinned Design Review handoff and verify lineage;
5. verify Assistant prompt-injection boundaries and the three planning MCP tools;
6. open the external Mold Planning route and read the canonical plan catalog;
7. require the catalog p95 to remain at or below 1,000 ms over ten external samples;
8. require exactly one running Mold AI Compose project and one application image shared by API,
   Web, MCP and both worker roles.

Sanitized evidence is written below `.runtime/evidence/mold-planning/` and is intentionally ignored
by Git.

## Release and recovery sequence

1. Run the complete backend, Engineering Web, Sites and Compose regression gate.
2. Stop any separate development Compose project; do not delete the active Sites Demo volumes.
3. rebuild `mold-ai-platform-app:0.14.0-demo` through `scripts/sites-demo-start.ps1`;
4. run `scripts/sites-demo-smoke.ps1`, `scripts/demo-performance.ps1` and the Mold Planning golden
   acceptance script;
5. verify the owner-only Sites portal, current HTTPS Quick Tunnel and Secure MCP Tunnel;
6. retain only `mold-ai-platform-sites-demo` as the active Mold AI Compose project and remove older
   Mold AI application image tags after the new image passes smoke;
7. use `scripts/demo-backup.ps1` before any future reset and the isolated restore/recovery scripts
   for continuity drills.

Quick Tunnel URLs remain ephemeral. The stable private Sites entry remains unchanged and stores
only the current Quick Tunnel origin in the browser session. The external Web uses a personal Mold
AI session; ChatGPT MCP uses the separate Secure MCP Tunnel and internal service identity.

## Release limitations

- the deterministic LLM fallback is a supported Demo mode; live provider UAT is optional;
- Quick Tunnel is for owner-only demonstration, not an Enterprise ingress topology;
- planning requirements state what must be checked but do not claim that geometry, CAE or trial
  evidence passed;
- production SSO/OAuth, company connectors, electronic approval and report templates remain
  Enterprise work.

## Verification evidence

The Phase 6 release gate passed on 2026-08-31:

- backend Ruff/check/migration gate: `238 passed`, `1 skipped`, `9 subtests passed`;
- Engineering Web: typecheck, `37` test files / `144` tests and production build;
- private Sites portal: lint, `2` test files / `15` tests and production build;
- PostgreSQL Golden Scenario: `33` isolated contract tests passed;
- external Mold Plan catalog: p95 `162.69 ms` over ten samples, below the `1,000 ms` gate;
- complete external performance baseline: Mold Plan catalog p95 `373.25 ms`, zero request errors;
- external smoke: local-account boundary, internal MCP service identity, HSTS, CSP, stable deep
  links and Plugin UI passed;
- MCP: `13` tools, including all three read-only Mold Planning tools;
- deployment: only `mold-ai-platform-sites-demo` is active and all five application roles use
  `mold-ai-platform-app:0.14.0-demo`;
- the older `mold-ai-platform-api:latest` and `mold-ai-platform-app:0.13.0-demo` images were
  removed after the new image passed smoke.

Runtime JSON evidence remains secret-free below `.runtime/evidence/` and outside Git.
