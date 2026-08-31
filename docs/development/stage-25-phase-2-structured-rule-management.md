# Stage 25 — Phase 2 Structured Rule Management

## Outcome

Phase 2 replaces rule-author JSON editing with a governed, structured workflow. Rule authors can now select a profile, create a draft from blank content, an approved template, or an existing version, edit applicability and rule fields, validate the draft, preview impact, compare versions, and move the version through the existing approval lifecycle.

Published and retired rule versions remain immutable. Every content change is written to a draft version, uses optimistic row-version checks, recalculates rule and applicability checksums, and records an audit event.

## Delivered capabilities

### Profile catalog and creation wizard

- Profile selector exposes all returned lifecycle states rather than silently using the first profile.
- Creation modes are `blank`, `template`, and `clone`.
- Template creation only accepts a Published or Retired governed source.
- Blank creation starts with no rules and must pass deterministic validation before submission.
- Profile key, version, reason, and change summary are entered as structured fields.

### Applicability editor

- Includes Mold Type, Product Type, Material, Molding Process, and Location dimensions.
- Values are selected from governed Engineering Reference Data.
- Each condition explicitly uses Include or Exclude matching.
- The API verifies every referenced code is active and belongs to the profile scope.

### Structured rule editor

- Rule ID, title, description, evaluator, operator, threshold, unit, tolerance, severity, risk type, recommendation, reference document, reference revision, enabled state, and order are editable without JSON.
- Evaluators are selected from the deterministic evaluator registry.
- Evaluator parameters are initialized from controlled UI defaults and preserved by the canonical contract.
- Rules can be added, disabled, removed from the draft membership, and reordered.

### Validation, impact, diff, and workflow

- Read-only validation preview reports typed issues for empty rule sets, duplicate IDs, unsupported evaluators/operators, missing titles/units, and incomplete references.
- Impact preview returns scope-bounded counts for Molds, Revisions, CAD artifacts, and historical reviews without changing domain data.
- Version diff reports added, removed, and modified rules with changed field names.
- Workflow actions cover Draft → Validated → In Review → Approved → Published, plus retirement.
- Segregation of duties continues to prevent a rule author from approving their own version.

## API additions

- `POST /api/v1/rule-profiles` accepts `blank`, `template`, or `clone` creation modes.
- `POST /api/v1/rule-profiles/{id}/validate` performs read-only deterministic validation.
- `POST /api/v1/rule-profiles/{id}/impact-preview` returns scope-bounded impact counts.

The existing profile detail, patch, diff, and lifecycle action endpoints remain compatible.

## User-interface behavior

The Mold Rules workspace is organized into Overview, Applicability, Rules, Version diff, Workflow, and Usage tabs. Responsive layouts collapse structured editors to one column on narrow screens, and a sticky save action makes unsaved draft state explicit. All new user-facing strings have Traditional Chinese translations.

The Applicability tab is presented to Traditional Chinese users as **適用範圍與選用條件** so that its effect is explicit: it controls when a rule set may be selected for a mold, product, material, molding process, or location. Each row exposes labelled Condition type, Condition value, and Selection behavior fields. Governed versions are disabled and visibly read-only. An authorized rule author can use **Create editable draft** directly from the tab, enter the next version and change summary, clone the selected immutable version, and continue editing on the newly selected draft. Saving still uses optimistic locking and the normal validation, review, approval, and publication workflow.

## Verification gate

Phase 2 is accepted only when:

- targeted governance and resolver API tests pass;
- the complete backend regression suite, lint, formatting, system check, and migration drift check pass;
- the complete Vue test suite, type check, and production build pass;
- the Sites frontend test and build remain green;
- Compose definitions still resolve all application services to one `mold-ai-platform-app` image;
- `git diff --check` reports no whitespace defects.

External Sites and MCP validation are intentionally performed again at the final Phase 6 release gate after all later phases have been integrated.
