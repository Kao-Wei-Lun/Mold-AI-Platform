from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from platform_core.knowledge import index_knowledge_document_v2
from platform_core.knowledge_models import dense_encode, sparse_encode
from platform_core.models import KnowledgeChunk, KnowledgeDocument


def _chunk_matches_current_pipeline(chunk: KnowledgeChunk) -> bool:
    dense = dense_encode(chunk.text)
    sparse = sparse_encode(chunk.text)
    return bool(
        chunk.embedding_v2_model == dense.model
        and chunk.embedding_v2_dimension == dense.dimension
        and chunk.embedding_v2_checksum == dense.checksum
        and chunk.sparse_encoder == sparse.encoder
    )


class Command(BaseCommand):
    help = "Validate or idempotently populate the CPU knowledge v2 hybrid shadow index."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write missing v2 chunk vectors. Without this flag the command is read-only.",
        )
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options) -> None:
        queryset = (
            KnowledgeDocument.objects.filter(
                ingestion_status=KnowledgeDocument.IngestionStatus.INDEXED,
                publication_status="published",
            )
            .select_related("artifact_version__artifact")
            .order_by("created_at")
        )
        if options["limit"] > 0:
            queryset = queryset[: options["limit"]]

        inspected = ready_documents = indexed_documents = expected_chunks = ready_chunks = 0
        stale_chunks = 0
        failures: list[dict[str, str]] = []
        for document in queryset.iterator():
            inspected += 1
            chunks = list(
                document.chunks.filter(index_status=KnowledgeChunk.IndexStatus.INDEXED)
                .only(
                    "id",
                    "text",
                    "embedding_v2_model",
                    "embedding_v2_dimension",
                    "embedding_v2_checksum",
                    "sparse_encoder",
                )
                .order_by("ordinal")
            )
            expected = len(chunks)
            ready = sum(_chunk_matches_current_pipeline(chunk) for chunk in chunks)
            expected_chunks += expected
            ready_chunks += ready
            stale_chunks += expected - ready
            if expected > 0 and ready == expected:
                ready_documents += 1
                continue
            if not options["apply"]:
                continue
            try:
                result = index_knowledge_document_v2(document)
                indexed_documents += 1
                ready_documents += 1
                ready_chunks += int(result["chunk_count"]) - ready
            except Exception as exc:  # report all failures for a resumable batch
                failures.append(
                    {
                        "document_id": str(document.id),
                        "code": str(getattr(exc, "code", "RAG_V2_MIGRATION_FAILED")),
                    }
                )

        payload = {
            "schema_version": "knowledge-index-migration@1.1",
            "mode": "apply" if options["apply"] else "validate",
            "inspected_documents": inspected,
            "ready_documents": ready_documents,
            "indexed_documents": indexed_documents,
            "expected_chunks": expected_chunks,
            "ready_chunks": ready_chunks,
            "missing_chunks": expected_chunks - ready_chunks,
            "stale_chunks": stale_chunks,
            "failures": failures,
            "activation_changed": False,
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))
        if failures:
            raise CommandError(f"Knowledge v2 migration failed for {len(failures)} document(s).")
