# Stage 40: CPU CAD v2 shadow index

## Outcome

This stage introduces a deterministic, CPU-only 32-dimensional geometry descriptor without changing
the active v1 similarity search. It creates a separate `cad-similarity-v2` collection contract and a
separate `cad-cpu-v2` index version so historical searches remain reproducible and rollback remains
possible.

## Safety and lineage

- Only the governed STL preview is read; the source CAD is not mutated.
- Classification, dataset, product and material scope are copied to the vector payload.
- The persisted feature set records the source and preview version IDs, preview SHA-256, unit state,
  deterministic seed, sample count and extractor versions.
- A repeated extraction with the same version tuple must reproduce the checksum or fails with
  `CAD_DESCRIPTOR_NONDETERMINISTIC`.
- Non-watertight meshes mark solidity `NOT_AVAILABLE`; no false volumetric claim is exposed.
- v2 dual-write is opt-in through `SIMILARITY_V2_SHADOW_INDEX`; v1 remains the read path.

## Verification

Focused tests cover rigid-transform and scale invariance, deterministic persistence, open-mesh
availability, typed missing-preview failure, 32-dimensional validation and ACL/version payloads.
The normal repository test gate must pass before this stage is committed.
