# Stage 22 — Historical Data Enterprise Hardening

## Outcome

Phase H7 completes the runnable Demo boundary for governed bulk operations and enterprise data separation. It does not claim that a customer PDM, MES, SIEM or identity provider has been connected.

The operator UI is available at:

```text
/data/enterprise?tab=policy
/data/enterprise?tab=import
/data/enterprise?tab=archive
```

## API surface

| Endpoint | Purpose | Required permission |
|---|---|---|
| `GET/PATCH /api/v1/enterprise/policy` | Scope connector, retention, legal hold, DLP, SIEM and namespaces | `enterprise:read/manage` |
| `GET/POST /api/v1/enterprise/import-batches` | List or validate a dry-run import batch | `enterprise:read`, `bulk:manage` |
| `GET/POST /api/v1/enterprise/import-batches/{id}` | Inspect or commit a validated batch | `enterprise:read`, `bulk:manage` |
| `POST /api/v1/enterprise/bulk-archive` | Dry-run or execute controlled archive | `bulk:manage` |

Every write requires a reason and creates an `AuditEvent`. A batch commit is idempotent, transactional and returns reconciliation counts. Invalid batches remain visible but cannot be committed.

## Public to Company connector cutover

1. Create a non-public `DataScope` and assign only authorized accounts.
2. Configure a Company policy with unique index and cache namespaces.
3. Keep `connector_mode=company`; a Public Demo scope is explicitly rejected for this mode.
4. Import a mapping sample with a unique idempotency key and review validation issues.
5. Commit only when `validation.valid=true`; confirm reconciliation is balanced.
6. Run scope-isolation, DLP export, audit and performance tests with production-like volume.
7. Connect the actual source adapter and secret manager only after owner/security approval.

Canonical domain contracts do not change during this cutover. Source-specific fields must be mapped before commit; the UI, capabilities and historical detail routes continue reading canonical records.

## Retention, legal hold and export

- Retention candidates are calculated using the scope policy cutoff; no automatic purge is enabled.
- Legal Hold blocks batch archive commits and protected Audit CSV export.
- DLP export uses the existing recursive secret redaction and a policy gate.
- SIEM configuration records readiness metadata only. Delivery credentials and an external transport are customer-environment dependencies.
- Hard delete remains unavailable through the Phase H7 API.

## Verification

Run from the repository root:

```powershell
docker compose run --rm api ruff check .
docker compose run --rm api python manage.py makemigrations --check --dry-run
docker compose run --rm api python manage.py history_performance_smoke --iterations 20 --budget-ms 800
docker compose run --rm web npm run test -- --run
docker compose run --rm web npm run build
```

The performance command is an ORM smoke budget on the current database. Before production cutover, repeat end-to-end API load tests using expected company volume, concurrency, network latency and object storage.
