# Stage 46F — Post-cutover v2 ingestion invariant

Status: implemented after external Demo acceptance found a post-cutover indexing gap.

## Incident

A CAD uploaded after the CPU v2 release completed its geometry job and v1 index, so the general UI
showed it as indexed. Similarity search correctly required a v2 FeatureSet and rejected the request.
The migration validator reported 26 ready artifact versions and one missing version.

## Corrected contract

- While v1 is active, `SIMILARITY_V2_SHADOW_INDEX` and `KNOWLEDGE_V2_SHADOW_INDEX` control optional
  shadow writes.
- Once the corresponding read route is `v2`, every successful new CAD or knowledge ingestion must
  write both the retained v1 index and the active v2 index, regardless of the shadow flag.
- Existing gaps remain recoverable with the resumable v2 migration commands.
- The fix does not synchronously perform heavy CAD extraction inside a search request; indexing
  remains part of the governed ingestion worker.

This prevents future records from presenting a generic indexed state while lacking the feature
contract required by the active route.
