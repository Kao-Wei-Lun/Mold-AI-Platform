# Stage 7 — Governed Process / Trial Case Analysis

## Delivered scope

Stage 7 implements the Demo Process/Trial vertical slice required by D-TRI-001–004 and UAT-03:

```text
SyntheticProcessTrialConnector
-> source version + raw-record hash + mapping version
-> TrialCase
   -> ProcessRun
      -> ProcessParameter
      -> DefectObservation
      -> CorrectiveAction
-> deterministic case ranking
-> compatible historical ranges or explicit abstention
-> Web evidence and approval boundary
```

The six fixtures are intentionally synthetic. They demonstrate contracts, lineage, ranking,
negative evidence, and guardrails; they are not production process knowledge and must not be used
to claim defect-rate improvement.

## Canonical data contract

`TrialCase` records machine, material lot, mold/part revisions, purpose, outcome, classification,
ACL scopes, and connector provenance. Each `ProcessRun` records a cycle range, environment, result,
and data quality. Parameters preserve canonical code, raw name, numeric value, canonical unit,
setpoint/actual kind, and sampling method. Defects preserve controlled code, severity, location,
rate, inspection method, and evidence. Corrective actions preserve before/after values, rationale,
approval, execution state, observed outcome, expected effect, stop condition, and evidence.

The seed endpoint is explicit and idempotent:

```http
GET  /api/v1/process-trial/demo-fixtures
POST /api/v1/process-trial/demo-fixtures
GET  /api/v1/trial-cases
GET  /api/v1/trial-cases/{trial_case_id}
```

Replaying the same source version returns existing records. If a raw fixture changes without a
source-version bump, ingestion rejects it instead of silently rewriting lineage.

## Public → Company Connector seam

`ProcessTrialConnector` defines five operations: `discover`, `extract`, `map`, `validate`, and
`health`. `SyntheticProcessTrialConnector` is the Demo adapter. A company adapter should implement
the same boundary and map MES, trial report, material, machine, and inspection identifiers into the
canonical graph. Ranking and Web code must remain independent of the raw source schema.

Before enabling company data, replace the Demo no-auth policy with tenant-scoped identity,
classification and row-level authorization, source-system credentials from a secret manager,
incremental checkpoints, dead-letter handling, reconciliation, and connector observability.

## Search and scoring contract

Create and retrieve persisted searches through:

```http
POST /api/v1/process-case-searches
GET  /api/v1/process-case-searches/{search_id}
```

The request accepts defect, material, machine, product type, location, canonical parameters, and
`top_k`. Stage 7 validates exact canonical units and supports:

- `injection_pressure_mpa` (`MPa`)
- `injection_speed_mm_s` (`mm/s`)
- `melt_temperature_c` and `mold_temperature_c` (`degC`)
- `holding_pressure_mpa` (`MPa`)
- `holding_time_s` and `cooling_time_s` (`s`)

`process-case-demo@1.0.0` uses available-lane reweighting:

| Lane | Base weight | Method |
|---|---:|---|
| Defect | 0.35 | controlled-code exact match |
| Material | 0.20 | canonical-code exact match |
| Machine | 0.15 | machine-code exact match |
| Product type | 0.10 | exact match |
| Location | 0.05 | controlled location exact match |
| Parameters | 0.15 | mean normalized numeric proximity |

Every result includes the profile version, lane scores, similarities, differences, parameters,
historical action/outcome, immutable evidence references, source hash/version, and data-quality
flags. The API persists the request snapshot and result and emits a hashed
`process.case_search.v1` audit event.

This score is a deterministic Demo retrieval heuristic. It is neither a probability nor a causal
root-cause model. Enterprise calibration requires expert-labeled golden and holdout datasets.

## Recommendation guardrails

Precise before/after values are copied only from a successful or improved case whose defect,
material, and machine match. An unresolved case can rank as evidence but cannot become a suggested
step. Every step contains the source case, evidence references, expected effect, stop condition,
association-only confidence, `requires_engineer_approval=true`, and `do_not_auto_apply=true`.

The service abstains when:

- `material_code` is missing (no cases or ranges are returned);
- `machine_code` is missing (case evidence may be shown, but ranges are withheld);
- no successful compatible case exists; or
- an input parameter is outside the Stage 7 validation bound.

The capability has no MES, PLC, OPC UA, or molding-machine write path. A future approved workflow
may export a change proposal, but direct automatic application remains outside this contract.

## Web behavior

The Process/Trial workspace loads connector status and the public Demo catalog, can explicitly seed
fixtures, submits canonical units, shows per-lane evidence, and separates a historical action from
a controlled-trial suggestion. Approval and no-auto-apply warnings remain visible beside each
step. Selecting “material not provided” demonstrates UAT-03 abstention.

## Verification and current limits

```powershell
.\scripts\test.ps1
.\scripts\smoke.ps1
```

Tests cover connector idempotency, canonical graph completeness, provenance, public Demo ACL,
ranking, evidence, persistence, audit hash, successful/negative outcomes, material/machine
compatibility, unit validation, parameter bounds, Web request mapping, guarded recommendations,
and running-stack UAT-03 behavior.

Stage 7 does not implement root-cause prediction, probability calibration, image-based defect
location, time-series acquisition, CAE/geometry fusion, company MES integration, or process-window
approval management. Those require representative company data, domain review, and separate
release gates.
