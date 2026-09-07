# CPU-only AI optimization implementation roadmap

Status: Active implementation  
Source specifications: SRS 18 (`cad-similarity-engine-optimization-srs.md`) and SRS 19
(`knowledge-rag-engine-optimization-srs.md`)

## Scope boundary

This work completes every planned function that can run on the single Windows/Docker CPU path.
GPU training, GPU inference, production company-data cutover and learned online ranking remain out of
scope. CPU delivery must preserve authorization, audit, lineage, deterministic manifests, rollback,
one application image and the owner-only external Demo boundary.

## Delivery stages

| Stage | CPU delivery | Acceptance gate |
| --- | --- | --- |
| 40 | Versioned CAD v2 shadow index and deterministic 32-dimensional shape invariants | rotation/translation/scale invariance, checksum repeatability, ACL payload, v1 coexistence |
| 41 | Manufacturing feature lanes and mold-family profile resolution | typed availability, STEP/STL policy, auditable effective weights, regression ranking |
| 42 | PCA/ICP alignment, signed/unsigned deviation and ROI comparison | quality gate, symmetry fallback, deterministic heatmap, ROI traceability |
| 43 | 2D/CAE metadata fusion and explicit user feedback | missing-lane renormalization, feedback authorization/audit, no online training |
| 44 | RAG structured parsing and hierarchical chunk/citation contract — implemented | parser sandbox gates, page/bounding-box locators, parent/child chunks, tombstone enforcement |
| 45A | Dense+sparse retrieval, RRF, CPU reranker and calibrated abstention — implemented | ACL before every stage, model provenance, deterministic fallback, offline evaluation |
| 45B | PDF citation viewer and bounding-box navigation — implemented | authorized same-origin source, page fallback, visual highlight accuracy |
| 45C | Model-free Docling CPU parsing and governed XLSX ingestion — implemented | no Torch/CUDA, table preservation, Office security gates, recorded fallback |
| 46 | Alias migration, rollback drill, benchmarks and external single-image release — implemented | parity, old-index retention, structural release gate, Sites/MCP smoke tests; expert Golden QA remains an approval gate |

Every stage updates its detailed development record, runs focused tests followed by the repository
gate appropriate to its risk, and is committed independently. No index becomes active in the same
step in which it is first created.

## Stage 40 contract

The v2 shadow descriptor is 32 dimensions: three principal-frame extent ratios, three principal
inertia shares, solidity, convexity, eight D2 bins, eight low-order 3D surface-Zernike power
coefficients and eight paired-normal-angle bins. Sampling is deterministic and records the seed,
sample count, source preview checksum, extractor version and missing-value policy. Open meshes do not
invent volume solidity; the lane is explicitly `NOT_AVAILABLE` and receives the declared zero fill
only inside the coarse vector.

The v1 collection stays active while `cad-similarity-v2` is populated. Stage 46 owns alias cutover
and rollback after evaluation; setting `SIMILARITY_V2_SHADOW_INDEX=true` only enables dual-write.
