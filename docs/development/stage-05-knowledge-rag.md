# Stage 5 — Governed Knowledge Retrieval

## Delivered scope

Stage 5 implements the first document Knowledge/RAG vertical slice:

```text
UTF-8 TXT / Markdown source
-> immutable ArtifactVersion + KnowledgeDocument
-> asynchronous knowledge.ingest@1.0.0 Job
-> prompt-injection / hidden-text scan
-> section and paragraph KnowledgeChunk locators
-> 64-dimensional deterministic feature-hash Qdrant index
-> server-derived ACL + classification pre-filter
-> lexical/vector/authority/freshness rerank
-> extractive claims + versioned citations, or explicit abstention
```

No LLM generates answers in this stage. Returned claims are source excerpts and every claim points
to a citation. This preserves an inspectable baseline before provider abstraction and generative
grounded-answer evaluation are introduced.

## Canonical records and provenance

`KnowledgeDocument` references one immutable `ArtifactVersion` and records document type,
authority, effective dates, owner, classification, ACL scopes, language, parser/chunker versions,
scan status, and ingestion status. `KnowledgeChunk` records source text hash, section/paragraph
locator, embedding version and vector, scan status, and index state.

A citation is identified by `artifact_version_id + chunk_id + locator`; a temporary URL is only a
convenience link. TXT/Markdown sources are served inline with a restrictive content security policy.

## Retrieval and authorization

The Demo principal scope is derived by the server as `public-demo`; the client cannot submit or
elevate principal scopes. Qdrant receives mandatory classification, ACL, and active-state filters
before candidate retrieval. PostgreSQL applies the same checks again before ranking, providing
defence in depth.

Hybrid Demo scoring is deterministic:

| Lane | Weight |
|---|---:|
| Query-token coverage | 0.55 |
| Feature-hash vector similarity | 0.25 |
| Authority | 0.15 |
| Effective-source freshness | 0.05 |

At least one query token must be supported by an authorized passage. Otherwise the system returns
`abstained=true`, no claims, and no citations.

## Ingestion safety

Stage 5 rejects non-UTF-8 data, unsupported formats, empty/oversized files, the EICAR test marker,
invalid effective dates, and exact duplicate content. Documents matching reviewed prompt-injection,
role-impersonation, prompt-disclosure, HTML-comment, or bidirectional-control patterns are
quarantined and never chunked or indexed.

This is a basic Demo scanner, not a replacement for malware scanning, DLP, PII/secret detection,
enterprise parser isolation, or curator review.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET/POST` | `/api/v1/knowledge-documents` | List or asynchronously ingest Demo documents |
| `GET` | `/api/v1/knowledge-documents/{document_id}` | Read provenance and ingestion state |
| `POST` | `/api/v1/knowledge-searches` | Retrieve authorized extractive evidence |
| `GET` | `/api/v1/knowledge-searches/{search_id}` | Read the persisted retrieval result |
| `GET` | `/api/v1/jobs/{job_id}` | Poll ingestion progress |

## Current boundaries

- Only UTF-8 TXT and Markdown are parsed; PDF/Office parsing and page coordinates are future work.
- Feature hashing is reproducible but not a learned semantic embedding.
- Only the public Demo ACL policy is exposed; SSO/group/tenant mapping is Enterprise scope.
- Obsolete sources are not indexed as active evidence.
- Process, Trial, CAE, and structured-case retrieval lanes are not yet implemented, so cross-lane
  Case ID fusion remains pending.
- LLM synthesis, claim verification, and provider fallback remain future stages.

## Verification

```powershell
.\scripts\test.ps1
.\scripts\smoke.ps1
```

The container smoke test ingests a unique Markdown guide, verifies chunks and source locators,
retrieves a grounded citation through the server ACL policy, and confirms abstention for an
unsupported query.
