# Stage 42: CPU registration, deviation and ROI evidence

## Outcome

Similarity results can now request an on-demand, persisted 3D comparison. The API applies
principal-axis coarse registration, conditionally runs bounded point-to-point ICP for candidates
whose ranking score is at least 0.80, produces a signed or unsigned surface-distance cloud and can
restrict the comparison to an explicit 3D ROI bounding box. The Web workspace exposes the operation,
statistics, ROI coordinates and an interactive blue/green/red point-cloud heatmap.

## API contract

`POST /api/v1/similarity-searches/{search_id}/candidates/{artifact_version_id}/comparison`
accepts an optional `{ "roi": { "min": [x,y,z], "max": [x,y,z] } }`. A candidate must already be
present in the authorized, completed search result; the API rejects direct object enumeration before
loading geometry. The persisted comparison is idempotent by search, candidate, ROI checksum and
algorithm version.

The response includes:

- `alignment_status`: `full` when ICP converges, `partial` when PCA is retained after an ICP limit,
  or `skipped` below the 0.80 score gate;
- the 4×4 rigid transform, PCA/final RMSE, convergence and symmetry-ambiguity evidence;
- signed deviations only when the query mesh is watertight with consistent winding; otherwise the
  mode is explicitly `unsigned`;
- bounded heatmap samples, tolerance, optional ROI score and a stable Lineage reference.

## Resource and safety boundaries

- Sampling is fixed at 1,536 points with a recorded seed; the Web payload is capped at 1,024 points.
- ICP is capped at 50 iterations and uses a 0.001 unit RMSE-delta convergence gate.
- Invalid/reversed ROI bounds and ROIs with fewer than 16 samples per model return typed errors.
- Every new persisted comparison writes an append-only Audit event; a repeated request returns the
  existing record without duplicating evidence.

## Verification

Tests cover rigid-transform convergence, low-score ICP skipping, signed/unsigned safety, ROI
validation, result-membership denial, persistence/idempotency, Web API integration and heatmap
render-state wiring. The full repository gate is required before commit.
