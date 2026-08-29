# Stage 23 — CAD Upload Governance Modes

## Outcome

CAD upload now separates exploratory engineering work from formal historical archiving. A user no
longer has to create or select a mold design revision merely to preview a STEP/STL file or run a
generic analysis. The choice is explicit in the Web UI and preserved in the Job input snapshot.

## User modes

| Mode | Mold revision | Intended use | Stored governance status |
|---|---|---|---|
| `quick_analysis` | Not accepted | Preview, geometry extraction, similarity and generic design review | `unassigned` |
| `governed_archive` | Required | Formal mold history, mold-specific rules, Trial/CAE linkage and release evidence | `governed` |

Quick analysis is the default. It does not mean temporary or untracked: the platform still creates
an immutable ArtifactVersion, Job, checksum and processing lineage. It only means the Artifact has
not yet been assigned to a governed MoldRevision. A future assignment workflow must add that
relationship with authorization and AuditEvent evidence; it must not rewrite the original file.

## API contract

`POST /api/v1/cad-artifacts` accepts the multipart field `ingestion_mode`:

- omitted: backward-compatible inference (`governed_archive` when `mold_revision_id` exists,
  otherwise `quick_analysis`);
- `quick_analysis`: rejects a simultaneous `mold_revision_id` to prevent ambiguous intent;
- `governed_archive`: requires a valid `mold_revision_id`.

The accepted response adds `ingestion_mode`, `governance_status` and `mold_revision_id`. The Job
`input_snapshot.source` records the same mode and governance state so an idempotent replay returns
the original record's meaning rather than silently reclassifying it.

Typed validation errors:

| Code | Condition |
|---|---|
| `VALIDATION_INGESTION_MODE` | Unknown mode or a quick-analysis request that also supplies a revision |
| `VALIDATION_MOLD_REVISION_REQUIRED` | Governed archive without a revision |
| `VALIDATION_MOLD_REVISION` | Supplied revision does not exist |

## UI behavior

- The upload purpose is selected before file metadata.
- Quick analysis explains which capabilities remain available and why formal history still needs a
  revision.
- Governed archive reveals the required related mold/design revision field and prefers the current
  released revision.
- If no active revisions exist, the UI directs the user to Mold Registry and the submit action
  returns a clear validation message.
- English and Traditional Chinese copy describe the engineering consequence rather than exposing
  database terminology.

## Verification

Automated coverage verifies default quick uploads omit `mold_revision_id`, governed uploads submit
the selected revision, the API persists each mode correctly, invalid combinations fail without
creating records, and the existing CAD processing suite remains compatible.

The external Demo acceptance gate remains:

1. rebuild the single `mold-ai-platform-sites-demo` Compose project;
2. pass API, worker, Web, authentication and curated-data readiness checks;
3. pass the HTTPS Sites smoke test;
4. confirm the public Web URL and MCP deep links still resolve to the same deployment.
