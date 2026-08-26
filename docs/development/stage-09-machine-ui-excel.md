# Stage 9 - Machine UI to reviewed Excel

## Delivered scope

Stage 9 implements the bounded Demo path for D-XLS-001 through D-XLS-004:

```text
PNG/JPEG upload or synthetic Demo screen
-> immutable HMI source ArtifactVersion + SHA-256
-> fixed, versioned screen profile and normalized regions
-> deterministic seven-segment recognition
-> value/unit/range validation and per-field confidence
-> mandatory human review for low-confidence values
-> versioned reviewed-parameter XLSX + audit/lineage sheet
```

This is deliberately not a general OCR claim. The Demo extractor recognizes four numeric fields
from `demo-generic-injection@1.0` only: injection pressure, injection speed, holding pressure, and
cooling time. Arbitrary layouts, perspective, fonts, languages, vendor screens, and production HMI
images require separately approved Enterprise profiles.

No image is sent to an LLM or cloud vision service in Stage 9.

## Canonical records and contracts

`HMIExtraction` references one immutable source image version and records the profile, extractor,
image dimensions, preprocessing disclosure, state, and review state. `HMIExtractedField` preserves
the raw recognized text, normalized numeric value and unit, confidence, normalized source bounding
box, validation state, original value, reviewer correction, reviewer identity, and timestamp.

`HMIExport` references a new immutable XLSX `ArtifactVersion`, its template version, and a SHA-256
of the reviewed field snapshot. Repeated exports create new artifact versions rather than replacing
past output. Audit events record review and export events with bounded details and payload hashes.

The response distinguishes:

- `value` / `unit`: extractor output;
- `effective_value` / `effective_unit`: reviewed value used by the workbook;
- `confidence`: extractor confidence, not engineering correctness;
- `source_region`: normalized image coordinates;
- `review_status`: `not_required`, `needs_review`, `confirmed`, `corrected`, or `rejected`.

## API

```http
GET  /api/v1/hmi/demo-fixture?variant=low-confidence|clean
GET  /api/v1/hmi-extractions
POST /api/v1/hmi-extractions                 multipart file + profile
GET  /api/v1/hmi-extractions/{extraction_id}
POST /api/v1/hmi-extractions/{extraction_id}/review
POST /api/v1/hmi-extractions/{extraction_id}/exports
GET  /api/v1/artifact-versions/{version_id}/download
```

The public Demo API returns only `public_demo` extraction records. Uploads accept actual PNG/JPEG
content up to 10 MB, verify decodability, apply EXIF orientation, reject unsafe dimensions, and
store content under a generated storage key rather than a user-supplied path.

## Confidence and human-review gate

The synthetic low-confidence fixture intentionally dims the holding-pressure segments. The numeric
value remains readable as `55.0 MPa`, but confidence falls below `0.90` and sets
`review_status=needs_review`. XLSX export returns `409 CONFLICT_REVIEW_REQUIRED` until an engineer
confirms or corrects every pending field. A rejected field keeps the extraction non-exportable.

Correction values must be numeric, use the profile's canonical unit, and remain in its approved
range. Confirmation never changes the extracted value; correction preserves both original and
reviewed values.

For the controlled clean fixture, all four critical numeric fields must match the known values. The
test corpus currently has four fields, so 4/4 exact matches exceeds the Demo gate of 95%; this is a
bounded fixture result, not a production OCR benchmark.

## Workbook contract

The workbook template is `reviewed-parameters@1.0.0` and has two sheets:

- `Parameters`: extraction metadata, typed numeric values, units, confidence, source regions,
  review status, reviewer, frozen header, table styling, and summary formulas;
- `Audit`: template/extractor versions, source artifact version and SHA-256, preprocessing,
  classification, and the non-layout-reproduction notice.

The exporter saves the workbook to memory, reopens it, and checks its sheet contract before the
artifact is persisted. Automated tests reopen the downloaded file, verify numeric cell types,
formulas, reviewed values, source hash, and absence of common formula error literals.

The preferred workspace spreadsheet runtime was unavailable in this Windows session, so the
repository implements a replaceable `openpyxl` exporter abstraction. The dependency is pinned to
`3.1.5`; visual design and workbook validation follow the project spreadsheet guidance. This is a
repository implementation detail and does not change the REST or artifact contract.

## Web behavior

The HMI workspace can load the bounded low-confidence fixture or accept a local PNG/JPG. It shows a
local preview, recognized fields, raw text, values, units, confidence, source coordinates, and the
profile/extractor versions. Low-confidence fields expose explicit confirmation and correction
controls. The XLSX action remains disabled until the API reports `ready_for_export`, then exposes
the immutable artifact download.

## Enterprise replacement path

Production rollout must add a versioned `HMIProfile` registry keyed by vendor, machine model,
firmware/language, screen identifier, coordinates/anchors, unit rules, accepted ranges, and
effective dates. The pipeline should add image-quality classification, calibrated orientation and
perspective correction, OCR/layout engines, profile confidence, reconciliation, approval workflow,
retention, field-level authorization where needed, and monitored queue workers.

Sensitive company screens must remain on approved infrastructure unless a security-approved cloud
vision route is explicitly configured. Company connectors and profiles must preserve source
artifacts, raw OCR, transformations, corrections, classification, ACL, parser/model versions, and
lineage. A formal representative-image evaluation set is required before expanding beyond the
synthetic profile.

## Verification and non-goals

```powershell
.\scripts\test.ps1
.\scripts\smoke.ps1
```

Tests cover exact clean-fixture recognition, confidence gating, confirmation/correction/rejection,
range and unit validation, image safety limits, public Demo listing, XLSX typing/formulas/lineage,
audit records, Web action states, and the running-container upload-review-export-download path.

Not implemented: general OCR, arbitrary perspective correction, production calibration, vendor
profiles, Excel template upload/designer, macro-enabled output, cloud vision, batch/asynchronous HMI
jobs, machine control, automatic parameter writes, or company data.
