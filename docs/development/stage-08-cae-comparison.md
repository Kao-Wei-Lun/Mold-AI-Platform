# Stage 8 — Structured CAE / Moldflow Run Comparison

## Delivered scope

Stage 8 implements D-CAE-001–004 as a transparent Demo example:

```text
SyntheticCAEConnector
-> source version + record hash + mapping version
-> CAEStudy
   -> CAERun
      -> CAEResult
-> run compatibility gate
-> compatible metric subset
-> deterministic metric deltas or blocked comparison
```

The Connector identifies its integration level as `synthetic_structured_export` and explicitly
reports `official_solver_api_connected=false`. It does not imitate or claim access to Autodesk
Moldflow APIs, proprietary result files, or a licensed solver. PDF and screenshot extraction remain
future fallback paths, not part of Stage 8.

## Canonical model

`CAEStudy` records solver family, product and mold revision references, material model, mesh family,
objective, owner, data classification, ACL scopes, and connector provenance. `CAERun` records exact
solver version, mesh artifact/checksum, material model, boundary and process settings, unit system,
status, immutable input hash, and data quality. `CAEResult` records metric code, scalar or region
count type, value, unit, location, field summary, quality flags, parser version, and source locator.

The five Demo studies contain one run and six metrics each:

- fill time;
- maximum injection pressure;
- minimum melt-front temperature;
- weld-line count;
- air-trap count; and
- maximum warpage.

Fixtures include a baseline, compatible candidate, solver-version mismatch, material-model
mismatch, and mesh-checksum mismatch. Values and outcomes are synthetic and are not solver ground
truth.

## Connector and endpoints

`CAEConnector` defines `discover`, `extract`, `map`, `validate`, and `health`. The Demo adapter can
be replaced by an authorized company connector without changing the canonical comparison or Web
contracts.

```http
GET  /api/v1/cae/demo-fixtures
POST /api/v1/cae/demo-fixtures
GET  /api/v1/cae-studies
GET  /api/v1/cae-studies/{study_id}
POST /api/v1/cae-comparisons
GET  /api/v1/cae-comparisons/{comparison_id}
```

Seed replay is idempotent. A source record that changes without a source-version bump is rejected
instead of silently replacing its provenance.

An Enterprise connector must use an API or result export permitted by the solver license, retain
the original artifact as an immutable `ArtifactVersion`, isolate the parser, record solver-specific
schema versions, reconcile incremental loads, and apply tenant authorization before returning a
study or run.

## Compatibility gate

`cae-run-compatibility@1.0.0` requires equality of:

- solver name and exact version;
- material model code/version;
- mesh checksum and mesh family;
- mold revision;
- unit system; and
- boundary settings.

Both runs must have `succeeded` status. Process settings may differ because they are an intended
comparison input. If any run-level rule fails, `compatible=false`, typed incompatibilities are
returned, and no metric delta is calculated.

After the run gate passes, only metrics present on both sides with the same metric code, result
type, unit, and no quality flag enter the compatible subset. Missing metrics, schema mismatches, and
quality-blocked metrics are reported separately and excluded rather than treated as zero.

## Result semantics and evidence

Each comparable metric returns baseline and candidate result IDs/values/locations, numeric and
percentage delta, deterministic finding, and evidence references containing both study IDs, run
IDs, result IDs, and the canonical metric code.

Lower is labeled better only for the Demo catalog's fill time, pressure, weld-line count, air-trap
count, and warpage indicators. Temperature change is always
`changed_review_required`; the system does not infer an acceptable temperature window. Findings
are typed `deterministic_metric_comparison`, separate from parsed facts and any future model or LLM
narrative.

The persisted comparison includes input hashes, compatibility profile, metric exclusions,
generation time, limitations, and `cae-comparison:{id}` lineage. A hashed
`cae.comparison_created.v1` audit event records the outcome without storing an unbounded payload in
the audit detail.

Stage 8 does not generate process settings, optimization proposals, or causal claims.

## Web behavior

The CAE workspace displays Connector status and the explicit no-official-API label, selects
baseline/candidate runs, shows the compatibility profile, blocks the metric table on incompatibility,
and presents compatible metric deltas with expandable result-level evidence. Parsed baseline,
candidate, and comparison lineage references remain visible below the table.

## Verification and limits

```powershell
.\scripts\test.ps1
.\scripts\smoke.ps1
```

Tests cover Connector idempotency, canonical field/unit/location parsing, public Demo ACL,
solver/material/mesh incompatibility, run status, missing/schema/quality-blocked metric exclusion,
delta precision, finding semantics, evidence completeness, persistence, audit hashing, Web request
mapping, and the running-container compatible/blocked flows.

Not implemented: proprietary result-file parsing, field-result visualization, mesh/region spatial
alignment, solver job submission, asynchronous CAE workers, optimization, CAE-to-Trial fusion, or
company data. These require licensed interfaces, representative data, engineering acceptance, and
separate security/performance release gates.
