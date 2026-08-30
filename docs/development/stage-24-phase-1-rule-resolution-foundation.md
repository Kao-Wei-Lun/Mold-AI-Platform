# Stage 24 Phase 1 — Engineering Reference Data and Rule Resolution

This stage implements Phase 1 of
[`15_Rule_and_Data_Ingestion_Enhancement_SRS.md`](../requirements/15_Rule_and_Data_Ingestion_Enhancement_SRS.md).
It keeps the existing `/governance/master-data` route and API contracts stable while replacing the
user-facing “Master data” wording with “Engineering reference data”.

## Delivered scope

- Adds governed `mold_type`, `molding_process`, and `rule_category` reference-data domains.
- Seeds eight editable Demo mold types, three molding processes, and five rule categories.
- Rejects arbitrary Mold Registry `mold_type` values at both create and update boundaries.
- Uses the same active Mold Type options in the registry create and historical-detail editors.
- Adds versioned rule-profile priority, default, effective period, scope, classification, resolution
  status, applicability checksum, and structured applicability entries.
- Resolves only published, effective, eligible, scope-visible profiles; ranks specificity before
  priority and fails closed on equal-ranked candidates.
- Supports an authorized manual profile override only with a reason and immutable Audit evidence.
- Persists resolution context, candidates, selected profile, reason, mode, and checksum on every
  Design Review so later profile publication cannot rewrite historical results.
- Shows the applied profile and “why selected” evidence in the Design Review UI.

## Compatibility and safety

- Legacy `product_scope`, `material_scope`, and rule-level `applicability` remain in place during the
  compatibility period.
- Migration `0016_rule_resolution_foundation` backfills the current published Demo profile without
  deleting or rewriting existing Review/Finding references.
- Inactive reference values disappear from new choices while historical codes remain readable.
- A profile with ambiguous specificity and priority blocks review instead of choosing arbitrarily.

## Verification gate

The stage is accepted only after these commands pass:

```powershell
cd services/platform-api
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\ruff.exe check platform_core
.venv\Scripts\python.exe manage.py test

cd ..\..\apps\web
npm test
npm run build
```

The external acceptance step rebuilds the single `mold-ai-platform-sites-demo` Compose project,
runs the repository Sites smoke test, and verifies that no second Mold AI Compose project or
application image remains.
