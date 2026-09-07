# Stage 44: CPU structured knowledge and citation contract

Status: Implemented and verified  
Requirement source: `19_Knowledge_RAG_Engine_Optimization_SRS.md` section 3.2 items 1–2 and
review gates RAG-GOV-002/003, RAG-SEC-001/002, RAG-CDM-001

## Outcome

Stage 44 replaces the original paragraph-only RAG ingestion contract with a deterministic,
CPU-only structured parser and hierarchy-aware chunker. The active search behavior remains on the
v1 index until Stage 45 creates and evaluates the hybrid v2 index.

The implementation provides:

- Markdown heading paths and table recognition;
- DOCX heading-style recognition and Word table conversion to Markdown while retaining the
  existing macro, external-link and archive-bomb controls;
- PDF page numbers, page dimensions and validated top-left point coordinates when the text matrix
  makes an estimated bounding box available;
- an explicit page-only fallback when a bounding box is absent or invalid;
- semantic-boundary prose splitting, intact tables up to 1,500 characters, and repeated table
  headers when a larger table is split;
- a stable parent section reference on every passage without indexing a duplicate parent passage;
- parser/chunker/source-checksum provenance in the database and Qdrant payload;
- deletion of named Qdrant points plus a canonical `tombstoned` chunk status when a document is
  retired.

## Versioned contracts

Parser: `structured-cpu@3.0.0`  
Chunker: `hierarchical-semantic@2.0.0`  
Chunk locator schema: `2.0`

Each locator contains `page_no`, `page_size`, `bbox`, `bbox_available`, coordinate origin/unit,
page rotation, heading `section_path`, `parent_ref`, paragraph and source offsets, and content type.
Coordinates use PDF points and a top-left origin. The current native PDF path reports
`estimated-text-run`, never `exact`; consumers must not imply pixel-perfect source geometry.

## Security and lifecycle boundaries

Source bytes still pass signature, maximum size/page count, encrypted PDF, PDF active content,
DOCX macro, external relationship, decompression-ratio, malware marker and prompt-injection gates
before indexing. Parsing performs no URL fetch and no external service call. Search performs a
second database authorization/publication check after vector candidate retrieval.

Retirement is deliberately two-layered: the database publication state blocks retrieval even if
Qdrant is delayed, while explicitly named points are deleted and chunks are marked with a
tombstone timestamp. Publishing a replacement also tombstones any previously published version.

## Stage 45C implementation update

The parser-neutral contract is now populated by the pinned model-free Docling CPU adapter for PDF,
DOCX, XLSX and Markdown. The native parser remains a recorded fallback and can be selected with a
feature flag. The adapter does not install Torch, CUDA, OCR or VLM models. Existing indexed versions
are not mutated automatically; Stage 46 owns controlled reindex and alias cutover.

## Verification

Automated coverage includes PDF page/bbox validation, invalid-bbox page fallback, DOCX heading and
table preservation, Markdown hierarchy, bounded semantic chunks, enriched Qdrant governance
payload, citation response contract, ACL recheck, and retirement tombstones. The repository gate
also covers migrations, all backend tests, the Vue application, Sites packaging, and Compose's
single application-image contract.
