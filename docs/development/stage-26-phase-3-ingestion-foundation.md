# Stage 26 — Phase 3 Unified Ingestion Foundation

## Outcome

Phase 3 introduces one governed ingestion state machine for structured engineering data. The previous Enterprise JSON batch endpoint remains available for backward compatibility, while new work uses `/api/v1/ingestions` and the Web Data Import Center at `/data/imports`.

No domain entity is written during upload, mapping, or Dry Run. Domain writes occur only in an atomic background commit after validation succeeds.

## Canonical ingestion records

- `BulkImportBatch` is retained as the physical migration-compatible batch table and now implements the canonical `IngestionBatch` contract.
- `IngestionSourceFile` links every uploaded or synthesized source to an immutable `ArtifactVersion`, SHA-256, MIME type, size, and screening result.
- `MappingProfile` stores versioned, scope-specific canonical field mappings.
- `IngestionIssue` stores row, field, typed code, raw value, suggestion, and blocking severity.
- `IngestionRecordResult` records each row as created, updated, skipped, or failed with its resulting entity ID.
- `ReconciliationReport` balances source, created, updated, skipped, and failed counts and stores a report hash.

The state machine is:

```text
draft → uploaded / mapping_required → validating
      → validation_failed
      → validated → queued → committing → committed
      → failed / cancelled
```

Committed batches are idempotent and cannot be committed twice.

## API and Web workflow

The new API supports list/create, detail, source upload, mapping, validation, issue retrieval, background commit, cancel, reconciliation, and template download. Responses contain a schema version, canonical ID, request ID, optional job correlation ID, and a Web deep link.

The Web workspace provides:

- data-scope and domain selection;
- CSV, XLSX, or JSON upload;
- immutable source screening evidence;
- canonical field mapping;
- Dry Run counts and row-level issues;
- explicit commit reason and background Job status;
- reconciliation evidence and import history.

A permission-aware global `＋新增資料` menu links users to batch import and existing single-record CAD, registry, engineering evidence, knowledge, and mold-rule workflows.

## Safety and recovery

- Idempotency keys cannot cross data scope or domain.
- Detail, issue, commit, cancel, and reconciliation endpoints return Not Found for records outside the user's scope.
- Commit is a single database transaction. Any row failure rolls back every domain write.
- Commit uses the general worker queue and the standard Job/JobEvent contract.
- Stale ingestion jobs are requeued with batch and actor arguments; exhausted jobs synchronize the batch to Failed.
- Source paths are generated from UUIDs and never use caller-supplied directory segments.
- Empty files and the EICAR test marker are rejected before persistence.

## Phase 3 supported adapters

The foundation carries forward the existing `master_data` and `projects` adapters. Phase 4A expands the same contracts to the remaining high-priority structured domains; Phase 4B adds engineering result and file-specific adapters. No second import implementation is introduced.

## Verification gate

Phase 3 is accepted when the complete automated gate passes, including explicit tests for:

- Dry Run zero domain writes;
- row-level typed validation issues;
- transaction rollback;
- duplicate idempotent delivery;
- scope isolation;
- source artifact screening and lineage identity;
- background commit and reconciliation;
- stale worker recovery;
- Vue type checking, component tests, bilingual strings, production builds, and Compose single-image validation.
