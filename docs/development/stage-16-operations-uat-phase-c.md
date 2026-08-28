# Stage 16 Phase C — Scoped Dataset Reset and Recovery Drills

Phase C completes the destructive-operation safety boundary without changing the active Sites Demo
during automated drills. It adds canonical dataset reset, a clean-room volume rebuild, and isolated
Qdrant/CAD-worker fault injection. The existing operations reset remains unchanged.

## Safety contract

- Reset defaults to a read-only preview.
- `operations` requires the exact phrase `RESET OPERATIONS`.
- `datasets` requires the exact phrase `RESET DATASETS`.
- `full-demo-volume` requires both `REBUILD ISOLATED DEMO VOLUMES` and the exact isolated project
  name as a second confirmation.
- Dataset and full-volume modes create a backup first. Dataset reset supports the existing explicit
  `-SkipBackup` operator override; full-volume mode never permits that override.
- Full-volume projects must be lowercase bounded names ending in `-rebuild-drill` and publish no
  host ports.
- Recovery projects must end in `-recovery-drill` and publish no host ports.
- No command accepts an arbitrary deletion path, broad Docker-volume selector, repository path,
  user home path, environment file, secret, or Tunnel profile as a deletion target.
- Cleanup uses only the already validated, exact isolated Compose project name.

## Dataset reset

Preview the current Sites Demo scope:

```powershell
.\scripts\demo-reset.ps1 -Mode datasets -DryRun
```

Execute after reviewing the preview:

```powershell
.\scripts\demo-reset.ps1 `
  -Mode datasets `
  -Confirmation "RESET DATASETS"
```

The confirmed reset removes all Demo Artifacts/ArtifactVersions, CAD/features/jobs/lineage/searches,
Review results/decisions, Knowledge documents/chunks/searches, Process/Trial records, CAE records,
HMI records and their explicitly identified CAD/Knowledge Qdrant points.

It preserves Similarity profiles, Rule profiles/RuleVersions, all existing Audit Events, environment
files, API keys, Tunnel profiles, Git history and Docker volumes. A confirmed run appends
`demo.datasets_reset.v1`.

After deletion, the wrapper runs `seed_demo_data`, forces `seed_cad_demo --reindex`, and requires
ready API plus reconciled curated CAD status. Vector deletion occurs before PostgreSQL deletion; if
Qdrant is unavailable, reset fails closed while canonical PostgreSQL and artifact data remain intact.

## Clean-room full-volume rebuild

```powershell
.\scripts\demo-reset.ps1 `
  -Mode full-demo-volume `
  -TargetProjectName mold-ai-check-rebuild-drill `
  -Confirmation "REBUILD ISOLATED DEMO VOLUMES" `
  -SecondaryConfirmation "mold-ai-check-rebuild-drill" `
  -CleanupAfterVerification
```

This creates a backup of the active selected Demo, then creates fresh PostgreSQL, Redis, Qdrant and
runtime volumes under the isolated target. It seeds every governed dataset, rebuilds CAD vectors,
runs a strict release snapshot and completes a real Celery job. `-CleanupAfterVerification` removes
only that validated project and its volumes. It does not restart or delete the active Sites Demo.

## Qdrant and worker recovery drill

```powershell
.\scripts\demo-recovery-drill.ps1 `
  -TargetProjectName mold-ai-check-recovery-drill `
  -Confirmation "RUN ISOLATED RECOVERY DRILL" `
  -CleanupAfterVerification
```

The drill proves that stopping Qdrant produces typed degradation without changing canonical counts,
re-index restores strict readiness, a CAD-queue task remains pending while `worker-cad` is stopped,
and the same task completes after the worker restarts. Sanitized JSON evidence is stored only below
ignored `.runtime/evidence`; it excludes URLs, secrets, Tunnel IDs, task IDs and container IDs.

## Verified implementation evidence (2026-08-28)

- Clean-room rebuild: Knowledge `1`, Process/Trial `6`, CAE `5`, curated CAD `16/16` with `16`
  indexed, strict snapshot passed and a Worker job completed.
- Dataset drill: removed `35` Artifacts, `35` ArtifactVersions, `17` FeatureSets, `5` Knowledge
  chunks and `22` vector points; canonical tables became empty while profiles and reset audit
  remained; reseed/re-index returned curated CAD to `16/16`.
- Recovery drill: typed Qdrant degradation, canonical preservation, successful re-index and queued
  CAD task completion after Worker restart passed in an isolated project.

## Remaining release gates

- Quick Tunnel interruption/recreation remains manual because stopping the active external Tunnel
  would interrupt the owner's live session.
- Different-network owner-only Sites UAT and ChatGPT account/workspace MCP UAT remain manual.
- Optional paid OpenAI provider UAT remains opt-in.
- CAD parse/similarity hardware microbenchmarks and final `1.0.0-demo` evidence/tag remain pending.
