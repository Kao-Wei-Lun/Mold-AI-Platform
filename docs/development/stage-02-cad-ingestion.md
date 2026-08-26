# Stage 2 — CAD Artifact and Job Vertical Slice

## Delivered scope

Stage 2 implements the first end-to-end engineering capability:

```text
STEP/STL multipart upload
-> immutable source ArtifactVersion
-> cad.parse@1.0.0 Job on the cad queue
-> CadQuery/OpenCascade or Trimesh processing
-> geometry metadata and derived STL ArtifactVersion
-> lineage edge
-> polling API and interactive Three.js preview
```

The source and preview are stored under server-generated keys. Storage paths are never returned to
the browser. Downloads go through an API endpoint and include `nosniff` and restrictive content
security headers.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/cad-artifacts` | Upload `.step`, `.stp`, or `.stl` and enqueue parsing |
| `GET` | `/api/v1/cad-artifacts` | List the 25 most recent source artifacts |
| `GET` | `/api/v1/cad-artifacts/{artifact_id}` | Read versions and jobs for one artifact |
| `GET` | `/api/v1/jobs/{job_id}` | Poll bounded progress, typed error, and result |
| `GET` | `/api/v1/artifact-versions/{version_id}/download` | Stream authorized artifact content |

Upload fields:

- `file` — required multipart file.
- `artifact_name` — optional display name.
- `dataset_id` — canonical dataset scope; defaults to `public-demo-v1`.
- `product_type` and `material_code` — optional canonical metadata used by similarity filters.
- `idempotency_key` — recommended; may alternatively use the `Idempotency-Key` header.

## Canonical records

- `Artifact` is the logical source or preview object.
- `ArtifactVersion` contains immutable content identity, SHA-256, media type, format, size, storage
  key, classification, source, and screening status.
- `Job` contains the immutable input snapshot and the `queued -> running -> succeeded/failed`
  state.
- `JobEvent` records each state/progress transition without overwriting prior events.
- `CADModel` contains parser/version, unit interpretation, bounding box, volume, surface area,
  face/edge counts, surface histogram, quality flags, and preview reference.
- `LineageEdge` links the derived preview to the exact input version and Job.

## Processing behavior

- STEP uses CadQuery 2.8 and OpenCascade in a short-lived subprocess. Native parser crashes are
  isolated from the queue worker. Internal geometry units are reported as millimetres.
- STL uses Trimesh 4.12. STL has no standard unit metadata, so `unit_system=unknown` and
  `UNIT_UNCERTAIN` are returned.
- Non-watertight meshes receive `OPEN_SHELL`; their volume is returned as unavailable rather than
  presenting an unreliable number.
- Preview output keys are deterministic, allowing safe replay of the same Job handler.

## Current security boundary

Stage 2 enforces supported extensions, STEP/STL content signatures, file-size limits, safe logical
filenames, SHA-256 calculation, isolated server-generated storage keys, and rejection of the EICAR
test marker. The API deliberately reports `basic_screened`, not `clean`.

A production malware scanner, authentication/authorization, tenant scope, audit policy, rate
limiting, signed download URLs, and parser container resource policy remain required before any
external or company-data deployment.

## Verification

Use [`fixtures/cad/tetrahedron.stl`](../../fixtures/cad/tetrahedron.stl) as a minimal upload sample
that contains no company data.

Run code-level quality gates:

```powershell
.\scripts\test.ps1
```

With the container stack running, exercise fresh STL tetrahedron and STEP box uploads through the
HTTP API, CAD queue, parsers, database, lineage, and preview download:

```powershell
.\scripts\smoke.ps1
```
