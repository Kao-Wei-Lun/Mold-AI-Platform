# Stage 18 Phase 2 — Governed Master Data

Status: implemented and externally deployable

Date: 2026-08-29

Requirements: DM-MST-001 through DM-MST-010

## Outcome

Phase 2 replaces engineering-form option literals with a governed canonical catalog. The Demo now
supports Dataset, Product Type, Material, Machine, Defect, Location and Unit through one consistent
model, API and bilingual administration workspace. The implementation remains within the existing
single `mold-ai-platform-sites-demo` Compose project and the unified
`mold-ai-platform-app:<version>` application image.

## Canonical contract

Every `MasterDataItem` carries:

- UUID, immutable `code`, `kind`, English and Traditional Chinese names/descriptions;
- active, inactive or archived lifecycle state and deterministic sort order;
- domain-specific `attributes` and aliases;
- `source_system`, `source_refs`, data scope, classification and effective dates;
- optimistic-lock `row_version`, actor references and created/updated timestamps;
- archive reason/time without hard-deleting historical codes.

Codes are unique case-insensitively within scope and kind. API updates reject code changes and stale
ETags. Inactive and archived values remain readable for historical records but are absent from the
active-options response used by new engineering forms.

## API

| Method and path | Purpose | Permission |
| --- | --- | --- |
| `GET /api/v1/master-data/options` | Grouped active options for engineering forms | `master-data:read` |
| `GET /api/v1/master-data` | Search, filter, sort and paginate the catalog | `master-data:read` |
| `POST /api/v1/master-data` | Create a controlled code | `master-data:manage` |
| `GET /api/v1/master-data/{id}` | Detail, ETag and reference summary | `master-data:read` |
| `PATCH /api/v1/master-data/{id}` | Update display data or lifecycle state | `master-data:manage` |
| `DELETE /api/v1/master-data/{id}` | Recoverable archive, never hard delete | `master-data:manage` |

List requests support `kind`, `status`, `search`, `sort`, `page` and `page_size`. Mutations use the
platform error envelope. A PATCH accepts either the exact weak `If-Match` ETag returned by the API or
the current `row_version`; stale edits return `409 CONCURRENT_MODIFICATION` with the current record.
All mutations require an individual local session, CSRF protection, the correct permission and an
auditable reason for update/lifecycle changes.

## Roles and audit

- All current governed roles receive `master-data:read` so engineering forms can load options.
- `data_steward` and `platform_admin` receive `master-data:manage`.
- Superusers inherit the same permissions through the platform-admin permission set.
- Create and update/archive operations append `master_data.created.v1` or
  `master_data.updated.v1` immutable AuditEvent records.

The migration updates existing roles, so the already-created external Demo administrator does not
need to be recreated.

## Seed and cache behavior

Migration `0009_governed_master_data` imports the public/synthetic baseline. The
`seed_master_data` management command is also run at API startup and is idempotent: it only inserts
missing records and never overwrites steward changes. The active options payload is cached for at
most 60 seconds and every successful mutation invalidates it immediately.

## Web experience

The permission-gated route `/governance/master-data` provides:

- seven domain tabs, bilingual display, search, lifecycle filter, ordering and pagination;
- create/edit forms with immutable-code guidance and JSON domain attributes;
- activate, deactivate and archive actions with change reason and confirmation;
- reference summaries so a steward can see historical use before a lifecycle change;
- a recoverable retry state when the Master Data API is unavailable.

CAD ingestion, CAD Similarity and Process/Trial receive their Dataset, Product Type, Material,
Machine, Defect and Location options from `GET /api/v1/master-data/options`. They do not silently
fall back to uncontrolled choices. The Process/Trial “Use explicit Demo inputs” action remains an
explicitly labelled synthetic test fixture, not a production fallback.

## External Demo and Docker boundary

No new Docker project or application image is introduced. Rebuild with the existing Sites Demo
overlay; the API migration runs before Gunicorn starts, the same Nginx web service serves the new
route, and the existing Cloudflare Quick Tunnel exposes it. After sign-in, an administrator can open:

```text
https://<current-quick-tunnel-host>/governance/master-data
```

The Quick Tunnel hostname may change after tunnel recreation; no fixed IP is required. The fixed
Sites portal continues to resolve the current Engineering Web entry URL through its existing remote
connection mechanism.

## Verification and acceptance

Automated coverage includes:

- idempotent seed and all seven option groups;
- create/list/search/update/archive, case-insensitive duplicate rejection and immutable code;
- ETag conflict, reference summary, role read/write separation and Audit creation;
- bilingual management UI, immutable-code control and managed creation;
- TypeScript, Vue unit tests, production builds, Django migration drift and full backend regression;
- release/Sites Demo Compose validation and unified application-image assertion.

External acceptance additionally checks migration state, the seven group counts, local-session page
access, current Quick Tunnel health and that only one Compose project owns the running Mold AI
containers.

## Deferred enterprise extensions

Company connectors can populate the same envelope but require approved source ownership, mapping,
read-only/override boundaries and reconciliation policy. Material supplier-grade detail, Machine HMI
profiles and formal alias/effective-date workflows can expand the `attributes` contract without
changing canonical identifiers or the engineering option API.
