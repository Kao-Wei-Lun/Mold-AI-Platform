# Stage 19 — Phase 3 Mold Registry and Governed CAD Artifacts

## Outcome

Phase 3 introduces the canonical engineering hierarchy required to manage CAD as a governed
record instead of an isolated upload:

`Project → ProductPart → Mold → MoldRevision → Artifact → ArtifactVersion`

The migration creates a synthetic `DEMO-CAD` project and maps the curated CAD corpus to explicit
molds and released revision `A` records. Original `ArtifactVersion` fields remain immutable.

## Delivered contract

- Project, product/part, mold and revision list/create/detail/update APIs.
- Scope-aware `registry:read` and `registry:manage` permissions.
- Unique project, part, mold and revision codes inside their owning hierarchy.
- Optimistic row-version checks and immutable canonical codes.
- Revision lifecycle: `draft → released → superseded → archived`.
- Releasing a newer revision supersedes the previous released revision.
- CAD uploads may be attached directly to a governed `MoldRevision`.
- Signature, size, SHA-256 and malware-test-marker screening remains active.
- Cross-artifact duplicate SHA-256 content is reported as a warning.
- Artifact lifecycle and quality management supports active, quarantine and archive states.
- Archive retains referenced engineering data; no hard-delete endpoint is exposed.
- Audit events are written for registry and artifact governance mutations.
- A bilingual Mold Registry workspace provides hierarchy counts and controlled creation flows.
- CAD upload now presents a governed mold-revision selector.
- CAD responses carry mold/revision, lifecycle and quality context, and return valid Web deep links.

## API routes

- `GET|POST /api/v1/registry/projects`
- `GET|PATCH /api/v1/registry/projects/{id}`
- `GET|POST /api/v1/registry/parts`
- `GET|POST /api/v1/registry/molds`
- `GET|PATCH /api/v1/registry/molds/{id}`
- `GET|POST /api/v1/registry/revisions`
- `GET|PATCH /api/v1/registry/revisions/{id}`
- `GET|PATCH /api/v1/registry/artifacts/{id}`

## Verification gate

- Registry permissions deny mutation for Viewer and permit Mold Engineer.
- Hierarchy relationships use `PROTECT` and unique database constraints.
- Revision state transitions and superseding behavior are tested.
- Artifact linking, quality transition and recoverable archive are tested.
- Existing CAD ingestion, processing, similarity, review and 3D preview tests remain in the full
  regression gate.
- Vue type checking, Registry component tests, CAD workspace tests and production build must pass.

## Demo / Enterprise boundary

The Demo uses local identities, the `public-demo` data scope and synthetic registry records. PDM/PLM
identifiers are represented by `source_system` and `source_revision_id`, but company connector
ownership and reconciliation remain Phase 7 concerns. No company schema or secret is embedded.
