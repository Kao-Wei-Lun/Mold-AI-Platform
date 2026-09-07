# Stage 45A: CPU hybrid retrieval, reranking and calibrated abstention

Status: Implemented and verified
Requirement source: `19_Knowledge_RAG_Engine_Optimization_SRS.md` section 3.2 items 3–5 and 7

## Outcome

This stage adds a shadowable v2 knowledge index with named dense and sparse vectors, Qdrant RRF,
CPU reranking, governed mold-domain query expansion and calibrated abstention. The v1 path remains
the default until Stage 46 migration and parity gates approve the alias/read cutover.

## Pipeline

1. Server-derived ACL, classification and dataset filters are placed on both Qdrant prefetches.
2. Dense and sparse candidates are fused by Qdrant RRF; raw dense and BM25-family scores are not
   linearly mixed.
3. The database rechecks scope, classification, effective dates, publication and tombstone state.
4. At most 30 authorized candidates enter the CPU reranker.
5. A versioned, approved threshold removes low-confidence passages; zero survivors produce the
   existing explicit abstention response.

The synonym dictionary currently covers shrink/sink mark, short shot, weld line and ejector stress
mark terminology in Traditional Chinese and English. Query expansions are recorded in each search.

## Model and dimension correction

The approved dense model is `BAAI/bge-small-zh-v1.5` through FastEmbed/ONNX CPU. FastEmbed's current
official model registry declares this model as 512 dimensions, not the 384 dimensions stated in the
earlier draft. The SRS and v2 collection contract were corrected to 512 before implementation.

`scripts/download_models.py` is the only connected model-prefetch operation. It downloads the
approved embedding and FlashRank model into `/data/models`, probes the dense dimension and writes a
SHA-256 file manifest. Runtime loaders use local-only caches. `RAG_CPU_MODELS_REQUIRED=true` makes
a missing or invalid package a typed startup/use failure; Demo can use a clearly recorded,
deterministic 512-dimensional embedding and lexical reranker fallback while preparation is pending.
Fallback results never claim the BGE or FlashRank identity.

## Versioned settings

- `QDRANT_KNOWLEDGE_COLLECTION_V2=knowledge-text-v2`
- `KNOWLEDGE_V2_SHADOW_INDEX=false`
- `KNOWLEDGE_INDEX_READ_VERSION=v1`
- `EMBEDDING_MODEL_PATH=/data/models/fastembed`
- `RERANKER_MODEL_PATH=/data/models/flashrank`
- `RAG_CPU_MODELS_REQUIRED=false`

The abstention record is
`platform_core/config/rag-abstention-v1.json`. A company-data release must replace the initial Demo
calibration with reviewed Chinese, English, bilingual, table, no-answer, near-miss, ACL-denial and
prompt-injection cases.

## Governance and lineage

Every v2 point includes document/chunk/version identifiers, ACL/classification, publication state,
parser/chunker/embedding versions and source checksum. Each canonical chunk retains dense model,
dimension/checksum and sparse encoder provenance. Retirement deletes explicitly named points from
both collections when v2 derivatives exist.

## Verification

Automated tests cover deterministic offline fallback, synonym and sparse determinism, approved
calibration, named-vector writes, identical ACL filters before both RRF prefetches, v2 provenance,
successful reranking and below-threshold abstention. Full repository tests remain the release gate.
