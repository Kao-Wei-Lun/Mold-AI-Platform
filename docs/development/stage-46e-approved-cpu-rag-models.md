# Stage 46E — Approved CPU RAG model activation

Status: implemented; runtime model assets are stored in the private persistent Demo volume.

## Activation sequence

1. Run `python scripts/download_models.py --target /data/models` in a connected preparation
   environment.
2. Preserve `/data/models/manifest.json`, which records model identities, licenses, file sizes and
   SHA-256 checksums.
3. Run `python manage.py migrate_knowledge_index_v2` and confirm fallback vectors are reported as
   stale after the active model changes.
4. Run `python manage.py migrate_knowledge_index_v2 --apply` and repeat validation.
5. Require the CPU AI release gate, grounded search smoke test and MCP smoke test to pass.

Runtime loading is local-only. The Web/API/worker processes do not download models, and no GPU,
CUDA image or second application image is introduced. If a model asset is unavailable and
`RAG_CPU_MODELS_REQUIRED=false`, the governed deterministic fallback remains available and records
the degraded model provenance.
