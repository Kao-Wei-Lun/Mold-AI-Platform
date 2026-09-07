# Stage 45C — CPU Docling and governed XLSX knowledge ingestion

Status: Implemented and verified
Requirement source: `19_Knowledge_RAG_Engine_Optimization_SRS.md` section 3.2 item 1 and
RAG-SEC-002

## Outcome

The governed Knowledge ingestion path now prefers Docling's model-free CPU pipelines for PDF,
DOCX, XLSX and Markdown. The implementation uses the targeted `docling-slim` extras and explicitly
does not install the `models-local` bundle, Torch, CUDA or OCR/VLM models.

The Web import and superseding-version flows accept XLSX in addition to TXT, Markdown, PDF and
DOCX. Spreadsheet rows are retained as Markdown tables for hierarchy-aware chunking and hybrid
retrieval.

## Runtime contract

- Package: `docling-slim[convert-core,format-pdf,format-docx,format-xlsx,format-markdown]` 2.126.0.
- PDF pipeline: `NativePdfFormatOption`, which is model-free and uses the native Docling parser.
- Parser identity: `docling-native-cpu@2.126.0`.
- Source input: an in-memory `DocumentStream`; URL inputs are never passed to Docling.
- Page limit: `DOCLING_MAX_PAGES`, default 200.
- File limit: the already validated source byte length, bounded by the 5 MB Knowledge upload gate.
- CPU threads: `DOCLING_CPU_THREADS`, exposed to the container as `OMP_NUM_THREADS`, default 4.
- Resilience: `DOCLING_REQUIRED=false` permits the existing secure parser as an explicit fallback;
  every fallback records `DOCLING_FALLBACK:<exception-type>` in parser warnings. Setting it to
  `true` converts parser failures into ingestion failures for strict acceptance environments.

## XLSX safety boundary

Before OpenPyXL or Docling sees the source, the upload pipeline verifies the ZIP signature,
required workbook member, archive member count, total expanded bytes and compression ratio. It
rejects VBA content and external Office relationships. Extraction uses read-only, cached-value and
no-external-link modes, and enforces these deterministic complexity limits:

- 100 worksheets;
- 10,000 rows per worksheet;
- 200 columns inspected per row;
- 50,000 populated cells per workbook.

The general malware marker and prompt-injection scans continue to run. Spreadsheet formulas are
not executed; only cached values are extracted.

## Compatibility and rollback

TXT remains on the deterministic native parser. The prior PDF/DOCX parsers remain available only
as the recorded fallback, so an operator can set `DOCLING_CPU_ENABLED=false` without changing the
chunk/citation schema. No database migration is required. Existing indexed versions remain
immutable until the Stage 46 controlled reindex command is run.

## Verification

- Safe XLSX extraction, Markdown table preservation and upload media type.
- Rejection of external XLSX relationships.
- Live Docling XLSX conversion with the pinned parser identity.
- Existing PDF bbox, DOCX hierarchy and archive-security regression suite.
- Frontend policy, picker, document import and superseding-version regression tests.
- Docker dependency inspection confirms `docling-slim 2.126.0` and no installed `torch` module.
