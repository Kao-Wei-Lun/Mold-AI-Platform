# Stage 4 — Deterministic Design Review

## Delivered scope

Stage 4 adds an auditable rule-evaluation vertical slice on top of parsed CAD geometry:

```text
CADModel + immutable ArtifactVersion
-> approved Demo RuleProfile and 13 RuleVersion records
-> asynchronous mold.design_review@1.0.0 Job on the CAD queue
-> registered deterministic evaluators (no eval or uploaded executable code)
-> PASS / FAIL / NOT_APPLICABLE / NOT_EVALUATED / ERROR findings
-> actual, limit, unit, rule version, geometry scope, quality flags, and evidence references
-> immutable reviewer decision history and hashed AuditEvent
-> Web evidence viewer and Accept / Reject / Waive workflow
```

The LLM is not part of the decision path. A future Assistant may explain persisted findings, but it
must not calculate or alter a rule result.

## Demo rule contract

`demo-general-design@1.0` is an approved, checksum-protected Demo profile. Its 13 synthetic rules
exercise overall dimensions, aspect ratio, volume, surface area, topology counts and ratios,
geometry quality flags, unit readiness, analytic surface share, rib ratio, and draft angle.

These thresholds are test fixtures, not production engineering guidance. Company thresholds must
arrive through a governed connector and pass technical review before promotion.

The evaluator registry maps a stored evaluator name to reviewed Python code. Rule records contain
parameters and comparison operators, never arbitrary Python, SQL, shell commands, or expressions.

## Measurement truthfulness

Stage 4 can automatically evaluate global values already supplied by the Stage 2 geometry parser.
It does not claim face-level rib thickness or draft extraction. The Web UI can provide controlled
Demo measurements for those two rules, and their findings are marked
`USER_SUPPLIED_DEMO_MEASUREMENT`. Without those inputs, the result is `NOT_EVALUATED`, never
`PASS`.

The current 3D evidence view emphasizes the whole model and displays the evidence scope. Stable
face IDs, automatic face measurement, and face-level highlighting remain future CAD-kernel work.

## Review decisions and audit

Reviewer actions are separate `ReviewDecision` records:

- `accepted`: reviewer accepts the failed finding for action;
- `rejected`: reviewer disputes it and must provide a reason;
- `waived`: an approver and reason are mandatory.

A decision never changes the deterministic `ReviewFinding.result`. Every decision creates an
`AuditEvent` with actor, target references, detail, and a canonical payload hash. Authentication,
RBAC, enterprise retention, and tamper-evident external audit storage are still required before
company-data or external-user use.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/rule-profiles` | Read the Demo profile and versioned rule catalog |
| `POST` | `/api/v1/design-reviews` | Create an asynchronous review from a parsed CAD version |
| `GET` | `/api/v1/jobs/{job_id}` | Poll progress and receive the completed review |
| `GET` | `/api/v1/design-reviews/{review_id}` | Read persisted findings and decisions |
| `POST` | `/api/v1/design-reviews/{review_id}/findings/{finding_id}/decisions` | Record a reviewer decision |

Example request:

```json
{
  "schema_version": "1.0",
  "idempotency_key": "ui-review-001",
  "cad_artifact_version_id": "00000000-0000-0000-0000-000000000000",
  "profile": "demo-general-design@1.0",
  "context": {
    "nominal_wall_thickness_mm": 2.0,
    "max_rib_thickness_mm": 1.5
  }
}
```

Only the three documented numeric context fields are accepted. Unknown fields and non-finite,
negative, or executable-looking payload structures are rejected before job creation.

## Verification

```powershell
.\scripts\test.ps1
.\scripts\smoke.ps1
```

The container smoke test processes a STEP fixture, runs all 13 rules, verifies PASS, FAIL, and
NOT_EVALUATED results, checks rib actual/limit/location evidence, records a waiver, and confirms the
original FAIL and audit-backed decision both remain persisted.
