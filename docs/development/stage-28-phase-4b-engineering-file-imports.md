# Stage 28 — Phase 4B Engineering File Imports

## Delivery sequence

| Adapter | Formats | Status |
|---|---|---|
| CAE Summary | CSV, XLSX, JSON | Complete |
| Knowledge secure parser | TXT, Markdown, PDF, DOCX | Complete |
| HMI batch | PNG, JPG | Planned |
| CAD artifact/version | STEP, STP, STL | Planned |

All Phase 4B paths retain immutable source artifacts and use the Phase 3 Ingestion Batch, typed issue, atomic commit, record result, reconciliation, audit, and job recovery contracts.

## CAE Summary adapter

The `cae_results` adapter maps one source row to a Study, Run, and structured Result hierarchy. It preserves solver/version, mesh references, material model, boundary/process settings, unit system, result location and field summary. Dry Run validates required fields, JSON objects, result/status enums, numeric values, duplicate metrics, unit references, and scope ownership without creating CAE entities. Commit is append-only and replay-safe: existing metrics are skipped rather than overwritten.

## Knowledge secure parser

Knowledge upload now supports TXT, Markdown, PDF, and DOCX. PDF processing rejects encryption, active actions, JavaScript, embedded files, malformed documents, and excessive page count. DOCX processing rejects malformed ZIP containers, unsafe entry count or expansion ratio, macros, and external relationships. Every format must yield text, passes the existing malware signature screen, and is scanned for prompt-injection patterns before indexing. Suspicious documents remain quarantined and cannot become retrieval evidence.
