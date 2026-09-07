# Stage 46B — Knowledge v2 resumable migration

Status: implemented; v1 remains the default read route.

## Delivered contract

- Existing published, indexed documents can be copied into the CPU hybrid v2 collection without
  deleting or recreating canonical chunks and without modifying the v1 collection.
- Dense and sparse encoder identity, dimension and checksum are persisted on every chunk.
- ACL, classification, publication state, parser/chunker versions and source checksum accompany
  every v2 point.
- `migrate_knowledge_index_v2` is read-only by default, reports document/chunk parity and supports
  resumable `--apply` operation.
- The migration never changes `KNOWLEDGE_INDEX_READ_VERSION`; activation belongs to the release
  gate after corpus and Golden QA validation.

## Operator sequence

1. `python manage.py migrate_knowledge_index_v2`
2. `python manage.py migrate_knowledge_index_v2 --apply`
3. Repeat the validation command and require `missing_chunks=0` and no failures.
4. Run the Stage 46 release gate before changing the read route to `v2`.
5. Roll back by restoring `KNOWLEDGE_INDEX_READ_VERSION=v1`; v1 was never deleted.
