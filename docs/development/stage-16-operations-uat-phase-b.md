# Stage 16 Phase B — Readiness, Stale-Job Recovery and Performance Evidence

Phase B adds explicit worker/recovery diagnostics and a reproducible, secret-free performance
baseline to the Phase A operator surface. It does not perform dataset/full-volume reset or claim
that manual different-network and ChatGPT workspace UAT have passed.

## Status contract

```powershell
.\scripts\demo-status.ps1
.\scripts\demo-status.ps1 -Json
```

The text view now exposes dependency health, responding Celery workers, canonical dataset counts,
core readiness, Sites/Quick Tunnel readiness, the selected security profile, MCP deep-link/tunnel
state and the optional Assistant state. `degraded` can still describe an optional deterministic
Assistant fallback; `readiness_summary.core=ready` and `external_access=ready` identify whether the
engineering Demo and private external path are actually usable.

Worker readiness requires two bounded Celery ping responses: the `general` worker and the `cad`
worker. Container presence alone is not considered proof that queued work can execute.

## Stale-job policy

Preview without changing records:

```powershell
docker compose exec -T api python manage.py recover_stale_jobs --stale-minutes 15 --json
```

Apply only after reviewing the candidate counts:

```powershell
docker compose exec -T api python manage.py recover_stale_jobs `
  --stale-minutes 15 `
  --apply `
  --confirmation "RECOVER STALE JOBS"
```

The bounded policy is:

- stale queued jobs with an approved capability-to-task mapping are submitted to their recorded
  queue again;
- stale running jobs below `max_attempts` return to queued state, clear runtime timestamps and are
  submitted again;
- stale running jobs at `max_attempts` fail with `JOB_HEARTBEAT_EXPIRED`;
- unknown capabilities fail closed with `STALE_JOB_UNSUPPORTED_CAPABILITY`;
- broker submission failure becomes `JOB_RECOVERY_QUEUE_UNAVAILABLE`;
- CAD, Knowledge and Design Review domain state is synchronized when recovery fails;
- every applied run appends a `demo.stale_job_recovery.v1` Audit Event.

The command accepts at most 1,000 candidates per run and stale thresholds from 1 to 1,440 minutes.
Its default is dry-run.

## Performance baseline

```powershell
.\scripts\demo-performance.ps1
.\scripts\demo-performance.ps1 -LocalDevelopment
```

The baseline records ten samples each for health, Demo status, CAD list, Trial list and CAE list,
then checks three concurrent Demo-status sessions and five queued Celery jobs. The default gate is
zero request errors and p95 at or below 5,000 ms. Evidence is written below ignored
`.runtime/evidence/performance` and contains no endpoint URL, token or key.

This is a reproducible Demo release signal, not a production capacity claim. It does not yet cover
CAD parse resource peaks, cold/warm similarity microbenchmarks or optional live-provider latency.
Those remain hardware/provider-specific profiles.

`demo-acceptance.ps1` now runs this baseline by default and adds `performance-baseline.json` to its
checksummed evidence bundle. `-SkipPerformance` is intended only for focused development checks;
a skipped performance gate cannot produce a release candidate.

## Remaining gates after Phase B

- dataset and full-volume reset modes with independent destructive-operation drills (completed in Phase C);
- automated Qdrant fault injection (completed in Phase C) and Quick Tunnel interruption UAT;
- CAD parse and similarity hardware microbenchmarks;
- manual different-network Sites UAT and ChatGPT account/workspace MCP UAT;
- optional paid-provider UAT;
- final evidence review and `1.0.0-demo` tag.
