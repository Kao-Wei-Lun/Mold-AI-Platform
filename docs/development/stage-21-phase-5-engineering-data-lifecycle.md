# Stage 21 — Phase 5 Trial, CAE and HMI Data Lifecycle

## Outcome

Phase 5 makes operational engineering evidence manageable in the platform while preserving the
source record. It implements the Demo scope defined by `DM-TRI`, `DM-CAE`, `DM-HMI` and acceptance
tests `DM-08`–`DM-10` in the data-management requirements.

The Engineering Web now exposes a permission-gated **Engineering data** workspace at
`/governance/engineering-data`. The same single Sites Demo deployment serves this route; no second
frontend or Docker project is introduced.

## Authorization

Two permissions are introduced:

| Permission | Purpose |
|---|---|
| `engineering-data:read` | Read public synthetic Trial, CAE and HMI lifecycle data. |
| `engineering-data:manage` | Create and transition governed operational records. |

All seeded roles receive read access. `mold_engineer`, `data_editor`, `data_steward` and
`platform_admin` receive management access. Existing request-level write authorization remains in
force, so a Viewer cannot bypass the domain permission by calling an API directly.

## Trial and Process contract

`TrialCase` has a lifecycle of `draft → closed → reopened → closed`, with an independent
`archived` terminal presentation state. Every mutation requires a reason and an optimistic
`row_version`.

- Draft and reopened metadata may be edited.
- Closing stamps `closed_at`.
- Closed source values are immutable.
- A post-close change creates a `TrialCorrectionRecord` containing before values, proposed after
  values, actor, reason and timestamp. It does not silently overwrite the source fields.
- Machine, material and product type accept active canonical master-data codes only.
- Unknown canonical values are rejected with `MASTER_DATA_MAPPING_REQUIRED` and retained in
  `MasterDataMappingBacklog`, including occurrence count and source reference.
- Payloads expose lifecycle, corrections, process runs, quality data and source provenance.

## CAE contract

The managed API creates `CAEStudy`, imports structured `CAERun` and `CAEResult` records and supports
archive/restore without hard deletion.

- Study code, governed mold revision, active material code, solver and mesh family are required.
- Structured results validate run status, result type, numeric value and uniqueness.
- Archived studies reject new run imports.
- Existing solver/material/mesh/unit/boundary compatibility checks remain the mandatory gate for
  comparison; Phase 5 does not weaken the deterministic comparison contract.
- Study responses expose source connector/version/hash/mapping metadata, run input hashes, parser
  lineage, quality flags and result-level evidence references.

The Demo accepts normalized structured metadata; official Moldflow APIs, solver license handling
and enterprise file parsers remain connector responsibilities.

## HMI contract

`HMIProfileVersion` versions the approved extraction layout and field schema. Its lifecycle is
`draft → published → retired`; publishing a new version retires the preceding published version.
An extraction may use only a published profile whose checksum matches the bounded Demo extractor.

Each `HMIExtraction` stores its exact profile-version foreign key. Human confirmation, correction
or rejection creates an immutable `HMICorrectionDecision`. Raw OCR text and normalized extractor
values remain unchanged; reviewed values are separate effective values. Existing XLSX export
continues to require a resolved review state and retains artifact/checksum lineage.

## API surface

| Method and path | Contract |
|---|---|
| `GET/POST /api/v1/trial-cases` | List or create governed Trial cases. |
| `GET/PATCH /api/v1/trial-cases/{id}` | Read or transition/update/correct one Trial. |
| `GET/POST /api/v1/cae-studies` | List or create structured CAE studies. |
| `GET/PATCH /api/v1/cae-studies/{id}` | Read, archive or restore a study. |
| `POST /api/v1/cae-studies/{id}/runs` | Import one structured run and its results atomically. |
| `GET/POST /api/v1/hmi-profiles` | List profiles or clone a draft version. |
| `POST /api/v1/hmi-profiles/{id}/actions` | Publish or retire a profile. |

The existing HMI extraction/review/export endpoints now include the profile definition and
correction decisions in their response contract.

## Schema migration

Migration `0012_caestudy_archive_reason_caestudy_archived_at_and_more.py`:

- expands Trial and CAE lifecycle fields;
- creates Trial and HMI correction records;
- creates HMI profile versions and the extraction relationship;
- creates the master-data mapping backlog;
- grants Phase 5 role permissions;
- seeds the compatible Demo HMI profile and backfills existing HMI extraction references;
- treats pre-existing synthetic Trial fixtures as closed historical evidence.

Rollback of schema operations must follow a database/artifact backup. Operational lifecycle data
must not be discarded by manually reversing the migration in a populated environment.

## Verification and acceptance

Automated tests cover:

- Trial create, close, immutable closed values, correction record and reopen;
- canonical value rejection plus Mapping Backlog capture;
- Viewer read access and mutation denial;
- structured CAE run/result import, archive and archived-import rejection;
- existing CAE compatibility regression;
- HMI profile clone/publish/retire, published-profile enforcement and profile lineage;
- raw OCR preservation, reviewed effective value and correction decision;
- Web route, governed master-data selections, audit reason and lifecycle summaries;
- full backend, Engineering Web, Sites Web, build and Compose regression gates.

## Enterprise boundary

Phase 5 is deliberately a public synthetic Demo implementation. Enterprise delivery still needs
MES/QMS/CAE connectors, source-authority policy, unit conversion governance, solver licensing,
connector reconciliation, retention/legal hold, bulk import dry-run and enterprise OIDC/service
identity. Those are not inferred or simulated as already available.
