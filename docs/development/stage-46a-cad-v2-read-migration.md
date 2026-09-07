# Stage 46A — CAD v2 read route and migration

Status: implemented; activation remains an explicit release action.

## Delivered contract

- `SIMILARITY_INDEX_READ_VERSION` accepts `v1` or `v2` and defaults to retained v1.
- A similarity job pins the selected feature set, schema, extractor, profile, collection and index
  version in its immutable input snapshot.
- v2 reads the 32-dimensional CPU collection and reranks with deterministic shape,
  manufacturing, dimension, topology, metadata and available cross-modal lanes.
- `migrate_cad_index_v2` is read-only by default; `--apply` idempotently fills the shadow index.
- Migration never changes the active read route or deletes v1.

## Operator sequence

1. `python manage.py migrate_cad_index_v2`
2. `python manage.py migrate_cad_index_v2 --apply`
3. Run the Stage 46 release gate before setting `SIMILARITY_INDEX_READ_VERSION=v2`.
4. Roll back by restoring `v1`; no reindex is required.
