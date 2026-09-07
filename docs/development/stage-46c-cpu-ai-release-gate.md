# Stage 46C — CPU AI release gate, aliases and rollback

Status: implemented for the owner-only Demo boundary.

## Release controls

- `CPU_AI_RELEASE_ROUTE=v1|v2` is the single default route switch for both CAD similarity and
  Knowledge retrieval. Domain-specific read-version variables remain emergency overrides.
- `cpu_ai_release_gate` checks relational source/index parity, vector dimensions and checksums,
  v1 retention, Qdrant collection availability and point counts.
- Optional flags create Qdrant snapshots, prepare migration aliases and perform an atomic alias
  rollback-to-v1/restore-to-v2 drill.
- The command records the CPU/Python environment and explicitly states that no GPU is required.
- A structural pass does not claim Recall, nDCG, MRR or citation quality. The 50-CAD and 100-question
  expert Golden sets required by SRS 18/19 remain a Domain Owner approval gate before enterprise
  production use.
- Manufacturing undercut ray evaluation is deterministically capped at 256 source faces. The
  sampled-area estimate and cap are recorded in the extractor manifest so large tessellations stay
  bounded on CPU and remain auditable.

## Controlled activation

1. Run both migration commands in validate mode, then `--apply`, then validate again.
2. Run `cpu_ai_release_gate --prepare-aliases --snapshot --rollback-drill` and retain its JSON.
3. Set only `CPU_AI_RELEASE_ROUTE=v2` and recreate the application roles from the one application
   image. Existing queued jobs retain their pinned feature/index snapshot.
4. Run backend, Web, Sites and MCP smoke tests.
5. Roll back in one configuration operation by restoring `CPU_AI_RELEASE_ROUTE=v1` and recreating
   application roles. Neither migration command deletes v1.

## Quality boundary

Demo structural readiness and software tests may pass before expert Golden data exists. This is
reported as `domain_approval_required`, never silently converted into a quality pass.
