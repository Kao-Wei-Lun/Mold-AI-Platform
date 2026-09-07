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
- Profile resolution returns its reason code, selected profile and original weights. Missing lanes
  are renormalized by the comparison engine and never silently scored as zero.

## Verification

Tests cover the STL downgrade, optional approximation, STEP evidence, planar parting classification,
two-slide/planar evidence wording and deterministic connector-family resolution.
