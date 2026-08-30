# Stage 30 — Phase 6 security, performance and release gate

Phase 6 closes the Demo release requirements in
`docs/requirements/15_Rule_and_Data_Ingestion_Enhancement_SRS.md`. It adds executable security and
10,000-row ingestion gates while reusing the already proven backup, isolated restore, Qdrant
rebuild, queue recovery and unified application-image operations.

## File ingestion security boundary

The common JSON/CSV/XLSX ingestion endpoint now enforces all of the following before preserving a
source artifact:

- the upload must remain within the configurable `MAX_INGESTION_UPLOAD_BYTES` boundary (25 MB by
  default);
- the filename suffix and declared MIME type must match the supported allow-list;
- CSV, JSON and XLSX string values beginning with spreadsheet formula-control prefixes are
  rejected; ordinary negative numeric values remain valid;
- XLSX formulas, hidden worksheets, macros, external links, embedded OLE content, excessive entry
  counts, excessive expanded size and unsafe compression ratios are rejected;
- filenames are reduced to their final path component before deterministic storage;
- the existing malware test signature screening, immutable ArtifactVersion, checksum, scope,
  classification, Audit and Lineage behavior remains mandatory.

These controls are deliberately a Demo-safe screening boundary. Enterprise deployment still needs
the approved anti-malware, DLP and object-storage services described by the SRS.

## Browser and authorization regression coverage

- Django SessionAuthentication rejects state-changing requests without a valid CSRF token.
- Ingestion detail lookup continues to return `404` when the batch belongs to another data scope.
- Vue renders server-provided issue messages through text interpolation; a hostile HTML payload is
  escaped and creates no executable DOM element.
- Existing enterprise export/DLP, role, scope, deep-link and MCP read-only tests remain part of the
  complete test suite.

## 10,000-row ingestion gate

Master-data Dry Run now loads existing scope identities in bounded set queries rather than issuing
one query per source row. Atomic Commit uses a 1,000-row `bulk_create` batch path for imports of 500
or more rows, while retaining the small-batch row path used for deterministic rollback fault tests.
Each source row still produces an `IngestionRecordResult`, and reconciliation must balance before
the batch is marked committed.

The automated test imports 10,000 unique material records and independently asserts that Dry Run
and Commit each complete within 60 seconds. On the Phase 6 development gate, the combined test call
completed in 1.05 seconds; production-like company infrastructure must be measured again before
Enterprise cutover.

## Verification evidence

The Phase 6A gate passed on 2026-08-30:

- backend: Ruff lint and format, Django check, migration drift check, `223 passed`, `1 skipped`,
  `9 subtests passed`;
- Engineering Web: typecheck, `32` files / `106` tests, production build;
- Sites portal: lint, `12` tests, production build;
- Compose: local, release, Sites Demo and restore-drill configurations validate; API, Web, MCP and
  both workers resolve to one `mold-ai-platform-app` image.

## Operational release sequence

1. Run `scripts/demo-backup.ps1` against the active Sites Demo.
2. Run `scripts/demo-restore.ps1` with a new bounded `*-restore-drill` project name; the script
   verifies checksums, restores canonical state and rebuilds Qdrant.
3. Run `scripts/demo-recovery-drill.ps1` to prove Qdrant degradation/recovery and Celery queue
   recovery without touching the active project.
4. Run `scripts/sites-demo-start.ps1` to rebuild the single application image and active Compose
   project.
5. Run `scripts/sites-demo-smoke.ps1`, `scripts/demo-status.ps1` and the Secure MCP tunnel check.
6. Verify the stable private Sites entry and an import deep link from a network path outside the
   local machine.

Runtime evidence belongs below ignored `.runtime/` paths. It must never contain account passwords,
API keys, tunnel control-plane keys or bearer credentials.

## Phase 6B recovery result

The 2026-08-30 operations drill produced a full secret-free backup with PostgreSQL, 47 artifact
files and SHA-256 manifests. An isolated restore verified the canonical database, artifact files
and 16/16 curated CAD index before deleting its temporary containers, networks and volumes. A
second isolated fault drill observed typed Qdrant degradation, preserved canonical records,
rebuilt both Knowledge and CAD indexes, retained a CAD task while its worker was stopped and
completed that task after worker restart.

The first clean-room fault attempt exposed a startup race: Compose considered the development API
container started while its migration process was still running. Recovery, restore and full-volume
rebuild scripts now call a shared API-readiness wait before any seed or verification command. The
entire fault drill passed after this correction. Release snapshots also include deterministic Audit
and ArtifactVersion manifest hashes, and restore now fails closed if either continuity check differs.
