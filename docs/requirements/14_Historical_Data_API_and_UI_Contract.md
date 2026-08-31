# Historical Data API and UI Contract

Status: implementation baseline
Contract version: `history-data-v1`
Applies to: Demo and Enterprise-ready history management

## 1. Scope

This contract defines the boundary between list pages, detail pages, governed mutations,
audit history, lineage and stable web routes. It does not change the canonical identifiers
or meaning of existing engineering records.

## 2. Current coverage baseline

| Domain | Existing model depth | Existing HTTP coverage | Existing UI coverage | Required work |
|---|---|---|---|---|
| Registry | Project, ProductPart, Mold, MoldRevision, Artifact | Project/Mold/Revision list and detail; Part list only; Artifact governance | Summary lists and create forms | Part detail, full record routes, references and version history |
| CAD | Artifact, ArtifactVersion, CADModel, FeatureSet | CAD list/create/detail, version download, jobs | Upload, recent selection, preview | History list/detail, versions, processing, features and lineage |
| Trial | TrialCase, ProcessRun, Parameter, Defect, Action, Correction | Governed list/detail/PATCH | Summary and lifecycle actions | Full nested detail and controlled child editing |
| CAE | Study, Run, Result, Comparison | Governed list/detail/PATCH, run create, comparison | Study summary and separate comparison workflow | Full nested detail, import UI and comparison history |
| HMI | ProfileVersion, Extraction, Field, CorrectionDecision, Export | Profile list/action, extraction list/detail/review/export | Current extraction review only | Extraction history, profile version, correction/export timeline |
| Knowledge | Document, Chunk, Search | Document list/detail/workflow/download; search list/detail | Upload, workflow, first eight summaries, search | Pagination, content/chunks, versions, citations and history |
| Rules | Profile, RuleVersion | Profile lists and workflow | First profile rules and workflow | Profile/version selector, draft editor and version diff |
| Review | ReviewRun, Finding, Decision | List/create/detail and decision | Current run context | Historical list, detail and run comparison |
| Similarity | Search and ranked result payload | List/create/detail | Current search context | Historical list, immutable detail and rerun |
| Process search | Search and result payload | List/create/detail | Current search context | Historical list and immutable detail |
| Jobs | Job, JobEvent | Job detail and recovery operations | Current job polling | List, event timeline and controlled retry/cancel |
| Audit | AuditEvent | No user-facing read API | None | Read-only list/filter/detail and entity timeline |
| Lineage | Foreign keys and provenance payloads | Distributed across domain payloads | Partial | Normalized graph/table contract |

## 3. Stable web routes

```text
/data/overview
/data/molds
/data/molds/{id}
/data/cad-artifacts
/data/cad-artifacts/{id}
/data/trials
/data/trials/{id}
/data/cae
/data/cae/{id}
/data/hmi
/data/hmi/{id}
/data/knowledge
/data/knowledge/{id}
/data/rules
/data/rules/{id}
/data/analysis-results
/data/analysis-results/{type}/{id}
/data/jobs
/data/jobs/{id}
/data/audit-lineage
```

Query state is shareable and reload-safe:

```text
?tab=results&run={uuid}&page=2&status=active&sort=-updated_at
```

No secret, access token, local file path or unredacted source credential may appear in a URL.

## 4. List contract

All history list endpoints converge on these query parameters:

| Parameter | Type | Meaning |
|---|---|---|
| `q` | string | Case-insensitive keyword search over approved fields |
| `status` | string/repeated | Lifecycle status filter |
| `project_id` | UUID | Authorized project scope |
| `mold_id` | UUID | Mold scope |
| `date_from` / `date_to` | ISO-8601 datetime | Creation or engineering event range |
| `sort` | string | Allowlisted field, prefix `-` for descending |
| `page` | positive integer | One-based page |
| `page_size` | integer | Default 25, maximum 100 |

Response:

```json
{
  "schema_version": "history-data-v1",
  "items": [],
  "page": 1,
  "page_size": 25,
  "total": 0,
  "sort": "-updated_at",
  "applied_filters": {}
}
```

List items contain identity, title/code, lifecycle, quality, timestamps and child counts only.
They must not serialize all process runs, CAE results, chunks, findings or corrections.

## 5. Detail contract

All detail responses contain this envelope in addition to domain content:

```json
{
  "schema_version": "history-data-v1",
  "id": "uuid",
  "record_type": "trial_case",
  "row_version": 1,
  "lifecycle_status": "draft",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "capabilities": {
    "edit": true,
    "correct": false,
    "archive": true,
    "download": false
  },
  "links": {
    "self": "/api/v1/trial-cases/{id}",
    "web": "/data/trials/{id}",
    "audit": "/api/v1/trial-cases/{id}/audit",
    "lineage": "/api/v1/trial-cases/{id}/lineage"
  }
}
```

The server is authoritative for `capabilities`; the client still handles `403` and lifecycle
conflicts because hidden buttons are not an authorization boundary.

### 5.1 CAD geometry detail projection

`Artifact.jobs[].result` is capability-dependent. A CAD artifact detail can contain `cad.parse`,
`mold.similarity_search`, `mold.design_review`, and future engineering job results in the same
history envelope. Clients must not cast every non-null Job result to `CADModel`.

The Geometry tab follows these rules:

- include only successful `cad.parse@*` jobs whose result passes the `CADModelResult` shape guard;
- calculate the Geometry tab count from that filtered collection, not from all non-null Job results;
- ignore non-CAD results without failing or hiding the rest of the record detail;
- show a governed empty state linked to the Jobs tab when no successful parsed geometry exists;
- preserve geometry metadata and FeatureSet evidence even when a preview is absent or deferred;
- require explicit user confirmation before downloading a preview of 12 MiB or larger, so a large
  tessellated STEP preview cannot block the history page before metadata is visible.

This is a client projection rule; Job history remains complete and immutable. Similarity, review,
and other analysis results remain available through their own tabs and historical result routes.

## 6. Mutation contract

Mutable requests include optimistic concurrency and a reason:

```json
{
  "row_version": 4,
  "reason": "Correct material lot from the signed trial sheet",
  "changes": {}
}
```

Mutation types:

- `PATCH /{resource}/{id}` for permitted draft or safe metadata fields.
- `POST /{resource}/{id}/actions` for lifecycle transitions.
- `POST /{resource}/{id}/versions` for a superseding immutable version.
- `POST /{resource}/{id}/corrections` for append-only corrections.
- No general-purpose history hard-delete endpoint.

Conflict response:

```json
{
  "code": "VERSION_CONFLICT",
  "message": "The record changed after it was loaded.",
  "request_id": "request-id",
  "details": {
    "expected_row_version": 4,
    "current_row_version": 5
  }
}
```

## 7. Audit contract

Audit is append-only and read-only through the application API.

```http
GET /api/v1/audit-events
  ?entity_type=&entity_id=&actor=&action=&date_from=&date_to=&page=&page_size=
```

Each event exposes an allowlisted and redacted representation of:

- event ID and timestamp;
- actor ID/display name and authentication source;
- action, entity type and entity ID;
- request ID, reason and decision;
- safe before/after summary;
- source IP only when policy permits.

Audit export requires `audit:export`, creates its own audit event and never exposes secrets.

## 8. Lineage contract

```json
{
  "schema_version": "history-data-v1",
  "root": {"type": "artifact_version", "id": "uuid"},
  "nodes": [
    {"type": "artifact_version", "id": "uuid", "label": "Housing A v2", "status": "ready"}
  ],
  "edges": [
    {"from": "uuid", "to": "uuid", "relation": "used_by_review"}
  ]
}
```

Allowed relation names are versioned. The UI provides both graph and accessible table views.

## 9. Immutable and versioned records

| Record | Mutation rule |
|---|---|
| ArtifactVersion binary/checksum | Immutable; replacement creates a version |
| Released MoldRevision | Immutable; design change creates a revision |
| Published RuleVersion | Immutable; clone to draft |
| Published KnowledgeDocument content | Immutable; create superseding version |
| Closed Trial snapshot | Correction or governed reopen only |
| CAEResult | Immutable; import a new run/study |
| HMI raw image/OCR | Immutable; append a review decision |
| Similarity/Review/Search/Comparison output | Immutable; rerun creates a result |
| JobEvent and AuditEvent | Append-only |

## 10. Permission baseline

The Demo may map several permissions to one local role, but APIs use resource permissions:

```text
trial:read trial:write trial:correct trial:reopen
cae:read cae:import cae:archive
hmi:read hmi:review hmi-profile:author
artifact:read artifact:metadata-write artifact:download
rule:author rule:review rule:approve rule:publish
knowledge:author knowledge:review knowledge:publish
job:read job:cancel job:retry
audit:read audit:export lineage:read
```

Author and approver separation remains mandatory for governed published content.

## 11. Error codes

| HTTP | Code | Use |
|---:|---|---|
| 400 | `VALIDATION_ERROR` | Invalid fields or query |
| 401 | `AUTHENTICATION_REQUIRED` | No authenticated principal |
| 403 | `PERMISSION_DENIED` | Authenticated but out of scope |
| 404 | `RECORD_NOT_FOUND` | Missing or intentionally concealed record |
| 409 | `VERSION_CONFLICT` | Optimistic concurrency failure |
| 409 | `INVALID_LIFECYCLE_TRANSITION` | State transition is not allowed |
| 422 | `DATA_QUALITY_BLOCKED` | Required quality gate failed |
| 423 | `RECORD_LOCKED` | Controlled lock prevents mutation |

Every error includes `code`, `message`, `request_id`, safe `details` and optional
`field_errors`.

## 12. H0 verification baseline

- Web: `25` test files, `83` tests passed.
- API: `161` tests passed, `1` skipped, `9` subtests passed using the isolated SQLite
  test configuration inside the development Docker image.
- The PostgreSQL compose environment is retained for runtime smoke tests; unit tests explicitly
  unset `POSTGRES_HOST` when verifying SQLite-specific operational snapshot behavior.

## 13. Phase acceptance linkage

| Phase | Contract sections implemented |
|---|---|
| H1 | Stable routes and reusable list/detail UI |
| H2 | Trial, CAE and HMI detail contracts |
| H3 | Registry/CAD detail, version and lineage contracts |
| H4 | Mutation, concurrency and lifecycle contracts |
| H5 | Rule/Knowledge version contracts |
| H6 | Analysis, Job, Audit and Lineage contracts |
| H7 | Pagination at scale, isolation, bulk and enterprise controls |

## 14. CAD geometry regression acceptance

- An artifact with one successful `cad.parse` job and one successful similarity job displays a
  Geometry count of `1` and renders exactly one geometry card.
- A capability result without `cad_model_id`, parser identity, geometry status, and quality flags
  is not rendered as geometry.
- A large preview first shows its size and a `Load 3D preview` action; metadata remains usable
  before the user starts the download.
- Selecting Geometry must never remove the artifact header or the rest of the detail workspace
  because another Job returned a different result schema.
