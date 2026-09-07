# Stage 43: CPU cross-modal constraints and explicit feedback

## Outcome

The similarity workspace can govern manual CTQ/tolerance and CAE summary evidence for a CAD version,
fuse comparable evidence into ranking, filter by physical-manufacturing constraints through the API,
and collect explicit engineer labels. This delivers the CPU portion of CAD SRS Phase 4 without
claiming that the Demo performs automatic drawing OCR or online learning.

## Cross-modal profile

Each CAD artifact version can have one version-checked engineering profile containing tolerance
strictness (`standard` or `precision`), CTQ count, optional surface roughness, flow-length ratio,
projected area, clamp-force band and gate type. The Web exposes these fields in an optional panel.
Create/update operations are audited and updates require the current `row_version`.

When both query and candidate have profiles, tolerance and CAE lanes receive 7.5% each. Existing
weights are scaled to retain a total of one. Missing evidence adds no lane and changes no score.
Filters for tolerance, clamp-force band and gate type are applied after authorized vector candidate
retrieval; candidates without the requested governed evidence are excluded.

## Feedback policy

The result detail exposes `Accept as reference` and an explicit `Not relevant` action. Negative labels
require one approved engineering reason. Feedback stores search, candidate feature, action, reason,
actor, scope, timestamp, idempotency key and retention expiry, and creates an append-only Audit event.
Browsing time and implicit skips are not captured as labels. The response advertises
`explicit-label-offline-only`; RankNet/metric learning remains an enterprise task and cannot run until
its separate data-volume and review gates are met.

## Verification

Tests cover profile creation and stale-update rejection, optional fusion and normalized weights,
negative-reason enforcement, idempotent feedback, candidate-scope denial and Web feedback wiring.
