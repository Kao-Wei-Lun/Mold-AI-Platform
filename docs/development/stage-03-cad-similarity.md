# Stage 3 — Explainable CAD Similarity

## Delivered scope

Stage 3 adds a deterministic similarity vertical slice on top of Stage 2 CAD parsing:

```text
parsed CADModel
-> versioned FeatureSet (12-dimensional normalized vector + raw engineering features)
-> classification/dataset-scoped Qdrant point
-> asynchronous mold.similarity_search@1.0.0 Job
-> coarse vector candidates
-> deterministic multi-lane reranking
-> persisted scores, evidence, profile/index versions, and lineage
-> Web ranked list and side-by-side 3D comparison
```

The LLM does not calculate or alter similarity scores. It may consume the persisted explanation in
a later Assistant/MCP stage.

The Web workspace can use the newly uploaded artifact or load any recent successfully indexed CAD
artifact as the query.

## Feature and scoring contract

`FeatureSet` records the exact feature schema, extractor version, normalized vector, checksum,
collection, index version, and index status. Stage 3 uses these score lanes:

| Lane | Evidence | Demo profile weight |
|---|---|---:|
| Geometry | Shape proportions, occupied bounding volume, normalized surface measure | 0.35 |
| Dimension | Sorted overall dimensions when unit systems are comparable | 0.25 |
| Topology | Face count, edge count, and surface-type distribution | 0.30 |
| Metadata | Available product type and material equality | 0.10 |

Unavailable lanes are removed and the remaining weights are normalized. They are never silently
scored as zero. STL dimensions retain `UNIT_UNCERTAIN`; absolute dimensions are only compared when
both records report the same unit interpretation.

The 12-dimensional vector is a coarse retrieval representation, not a learned CAD embedding. A
learned visual/shape embedding and face correspondence remain future work and are explicitly listed
in every result's limitations.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/similarity-searches` | Create an asynchronous search from an indexed CAD version |
| `GET` | `/api/v1/jobs/{job_id}` | Poll search progress and receive the completed result |
| `GET` | `/api/v1/similarity-searches/{search_id}` | Read the persisted result by search ID |

Example request:

```json
{
  "schema_version": "1.0",
  "idempotency_key": "ui-search-001",
  "query": {"cad_artifact_version_id": "00000000-0000-0000-0000-000000000000"},
  "filters": {
    "dataset_ids": ["public-demo-v1"],
    "product_types": ["housing"],
    "material_codes": ["PC_ABS"]
  },
  "top_k": 5
}
```

Every Qdrant query applies the query artifact classification as a mandatory native filter. Optional
dataset/product/material filters are also translated to Qdrant filters before candidate retrieval.

## Current boundaries

- Public/synthetic demo data only; authentication, tenant ACL enforcement, and audit events remain
  mandatory before external or company-data use.
- Metadata is supplied at upload time. Company connector mappings will later populate the same
  canonical fields.
- Qdrant failure does not destroy completed geometry. The CAD result is marked
  `SIMILARITY_INDEX_UNAVAILABLE`, and search is refused with a typed error until it is reprocessed.
- There is no learned visual embedding, local feature correspondence, relevance feedback training,
  or enterprise golden-dataset calibration in this stage.

## Verification

```powershell
.\scripts\test.ps1
.\scripts\smoke.ps1
```

The Docker smoke test uploads fresh STL and STEP fixtures, verifies FeatureSet indexing in Qdrant,
runs an asynchronous search, excludes the query itself, and checks scores, evidence, lineage, and
the persisted result endpoint.
