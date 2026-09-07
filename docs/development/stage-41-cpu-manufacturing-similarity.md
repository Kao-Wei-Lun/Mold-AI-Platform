# Stage 41: CPU manufacturing similarity lanes

## Outcome

The v2 CAD feature contract now records wall-thickness distribution, draw direction, undercut/slide
complexity and parting-line classification as a separate manufacturing lane. Three approved Demo
profile families (`housing-standard`, `precision-connector`, `optical-lens`) and a deterministic
general fallback resolve from governed product metadata.

## Precision contract

- STEP sources are evaluated from the governed tessellated preview and are explicitly labelled
  `APPROXIMATE`; the system does not present mesh evidence as exact B-Rep measurement.
- STL manufacturing evidence is `NOT_AVAILABLE` by default and therefore removed from effective
  weights. `SIMILARITY_STL_APPROXIMATE_THICKNESS=true` exposes approximate wall thickness only;
  undercut and parting evidence remain unavailable.
- Ray casting uses a fixed seed and bounded sample count. The manifest records source format,
  watertightness, draw-axis policy and extractor version.
- Profile resolution returns its reason code, selected profile and original weights. The comparison
  engine still reports normalized effective weights for available lanes, but the published Overall
  score is multiplied by `evidence_coverage` so sparse evidence cannot be presented as a
  high-confidence match. `available_lane_score`, `evidence_coverage` and `score_policy` make this
  treatment explicit rather than silently substituting zeroes.
- Unknown units are not dimension evidence. STEP/B-Rep and STL triangle counts are also not treated
  as comparable topology merely because both records contain face and edge counts.
- Datasets configured by `SIMILARITY_EXCLUDED_DATASETS` are omitted from normal candidate results.
  The Demo default excludes `curated-cad-demo-errors-v1`, whose intentionally broken open-shell
  model remains available for validation tests but never appears as a recommended reference.
- V2 results include localized major-similarity and major-difference evidence. Missing dimensions,
  metadata, topology or manufacturing lanes produce an explicit explanation instead of an empty
  panel.

## Verification

### Public CAD evaluation follow-up (2026-09-07)

New searches snapshot `SIMILARITY_GEOMETRY_POLICY` (default `block-distance@1.0`). V2 coarse
retrieval retains the existing vector; reranking compares independent normalized descriptor blocks.
Results expose `geometry_ranking` with policy, block scores/coverage and explicit legacy fallback.
Historic jobs without the snapshot retain cosine comparison. Set the policy to `cosine-v2` for
new-search rollback; no feature/index migration or data deletion is needed.

STL triangle counts are no longer scored as topology, including STL-to-STL pairs. STEP and STP
are treated as B-Rep representations. Scores remain uncalibrated relevance, not reuse probabilities;
the UI explicitly states that independent human-labelled evaluation is still outstanding.
See [public CAD evaluation plan](../planning/public-cad-similarity-evaluation-plan.md).

Tests cover the STL downgrade, optional approximation, STEP evidence, planar parting classification,
two-slide/planar evidence wording, deterministic connector-family resolution, evidence-coverage
scoring, V2 explanations and exclusion of error-control datasets.
