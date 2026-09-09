# Stage 23 — CAD Upload Governance Modes

## Outcome

CAD upload separates exploratory engineering work from formal historical archiving. A user no
longer has to create or select a mold design revision merely to preview a STEP/STL file or run a
generic analysis. The Web UI uses an upload-first flow and exposes the governed assignment as an
audited post-upload action, while the API continues to preserve both modes for compatibility.

## User modes

| Mode | Mold revision | Intended use | Stored governance status |
|---|---|---|---|
| `quick_analysis` | Not accepted | Preview, geometry extraction, similarity and generic design review | `unassigned` |
| `governed_archive` | Required | Formal mold history, mold-specific rules, Trial/CAE linkage and release evidence | `governed` |

Quick analysis is the default. As of Stage 52, an unassigned CAD is a temporary analysis file:
it may initiate similarity searches but cannot appear as another search's reference candidate.
Temporary does not imply automatic deletion: the platform still creates an immutable ArtifactVersion,
Job, checksum and processing lineage. It has not yet been assigned to a governed MoldRevision.
The post-upload assignment workflow adds that
relationship with authorization, optimistic locking, an operator-entered reason and AuditEvent
evidence; it does not rewrite the original file.

The default path creates a new CAD Artifact. A collapsed advanced option lets an authorized user
select an existing active CAD Artifact and upload the next immutable ArtifactVersion, preserving
the Artifact identity, prior versions and prior engineering results.

## API contract

`POST /api/v1/cad-artifacts` accepts the multipart field `ingestion_mode`:

- omitted: backward-compatible inference (`governed_archive` when `mold_revision_id` exists,
  otherwise `quick_analysis`);
- `quick_analysis`: rejects a simultaneous `mold_revision_id` to prevent ambiguous intent;
- `governed_archive`: requires a valid `mold_revision_id`.

The accepted response adds `row_version`, `ingestion_mode`, `governance_status` and
`mold_revision_id`. `row_version` is the authoritative optimistic-lock value for an immediate
post-upload governance update; clients must not assume that a fresh or replayed Artifact is version
zero or one. The Job
`input_snapshot.source` records the same mode and governance state so an idempotent replay returns
the original record's meaning rather than silently reclassifying it.

Typed validation errors:

| Code | Condition |
|---|---|
| `VALIDATION_INGESTION_MODE` | Unknown mode or a quick-analysis request that also supplies a revision |
| `VALIDATION_MOLD_REVISION_REQUIRED` | Governed archive without a revision |
| `VALIDATION_MOLD_REVISION` | Supplied revision does not exist |

## UI behavior

- New Artifact + quick analysis is the primary, low-friction path.
- A collapsed advanced section restores “add version to existing CAD” without burdening first-time
  uploads.
- After successful processing, action cards offer Revision linking, similarity search and design
  review without losing the active CAD context.
- The selected local file summary remains visible after a successful upload. The App-level session
  keeps the selected `File`, accepted upload metadata and parsed CAD result together, so leaving the
  CAD route and returning restores the preview and the “What would you like to do next?” actions.
  Choosing a catalog CAD clears the local upload context to prevent mixed identities.
- Revision linking requires a selected revision and a human-entered reason, and submits the
  `row_version` returned by the upload response.
- If no active revisions exist, the UI directs the user to Mold Registry and the submit action
  returns a clear validation message.
- English and Traditional Chinese copy describe the engineering consequence rather than exposing
  database terminology.

## Verification

Automated coverage verifies default quick uploads omit `mold_revision_id`, a new version sends the
existing `artifact_id`, the accepted response includes `row_version`, post-upload linking submits
the authoritative version and reason, selected-file and post-upload actions survive SPA route
round trips, the API persists each mode correctly, invalid combinations fail without creating
records, and the existing CAD processing suite remains compatible.

The external Demo acceptance gate remains:

1. rebuild the single `mold-ai-platform-sites-demo` Compose project;
2. pass API, worker, Web, authentication and curated-data readiness checks;
3. pass the HTTPS Sites smoke test;
4. confirm the public Web URL and MCP deep links still resolve to the same deployment.
