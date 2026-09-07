from __future__ import annotations

import json
import platform
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from platform_core.models import CADModel, FeatureSet, KnowledgeChunk, KnowledgeDocument
from platform_core.vector_store import (
    collection_info,
    create_collection_snapshot,
    exact_point_count,
    replace_collection_alias,
)


class Command(BaseCommand):
    help = "Run the CPU AI v2 structural release gate and optional Qdrant rollback drill."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--prepare-aliases", action="store_true")
        parser.add_argument("--snapshot", action="store_true")
        parser.add_argument("--rollback-drill", action="store_true")
        parser.add_argument("--skip-qdrant", action="store_true")

    def handle(self, *args, **options) -> None:
        started = time.perf_counter()
        cad_expected = CADModel.objects.filter(
            geometry_status=CADModel.GeometryStatus.SUCCEEDED,
            preview_artifact_version__isnull=False,
        ).count()
        cad_ready_query = FeatureSet.objects.filter(
            cad_model__geometry_status=CADModel.GeometryStatus.SUCCEEDED,
            cad_model__preview_artifact_version__isnull=False,
            feature_type="cad_similarity",
            schema_version="2.0",
            extractor_version="2.1.0",
            vector_dimension=32,
            index_status=FeatureSet.IndexStatus.INDEXED,
        )
        cad_ready = cad_ready_query.count()
        cad_contract_invalid = sum(
            1
            for feature in cad_ready_query.only("vector", "vector_checksum")
            if len(feature.vector) != 32 or len(feature.vector_checksum) != 64
        )

        knowledge_documents = KnowledgeDocument.objects.filter(
            ingestion_status=KnowledgeDocument.IngestionStatus.INDEXED,
            publication_status="published",
        )
        knowledge_chunks = KnowledgeChunk.objects.filter(
            document__in=knowledge_documents,
            index_status=KnowledgeChunk.IndexStatus.INDEXED,
        )
        knowledge_expected = knowledge_chunks.count()
        knowledge_ready = (
            knowledge_chunks.exclude(embedding_v2_model="")
            .filter(
                embedding_v2_dimension__isnull=False,
            )
            .count()
        )

        checks = {
            "cad_nonempty": cad_expected > 0,
            "cad_db_parity": cad_expected == cad_ready,
            "cad_vector_contract": cad_contract_invalid == 0,
            "knowledge_nonempty": knowledge_expected > 0,
            "knowledge_db_parity": knowledge_expected == knowledge_ready,
            "retained_v1_cad": FeatureSet.objects.filter(
                schema_version="1.0", index_status=FeatureSet.IndexStatus.INDEXED
            ).exists(),
            "retained_v1_knowledge": knowledge_chunks.exclude(embedding=[]).exists(),
        }
        qdrant_counts: dict[str, int] = {}
        snapshots: dict[str, object] = {}
        alias_events: list[dict[str, str]] = []
        if not options["skip_qdrant"]:
            collections = {
                "cad_v1": settings.QDRANT_CAD_COLLECTION,
                "cad_v2": settings.QDRANT_CAD_COLLECTION_V2,
                "knowledge_v1": settings.QDRANT_KNOWLEDGE_COLLECTION,
                "knowledge_v2": settings.QDRANT_KNOWLEDGE_COLLECTION_V2,
            }
            for label, name in collections.items():
                collection_info(name)
                qdrant_counts[label] = exact_point_count(name)
            checks["cad_qdrant_parity"] = qdrant_counts["cad_v2"] >= cad_ready
            checks["knowledge_qdrant_parity"] = qdrant_counts["knowledge_v2"] >= knowledge_ready
            if options["snapshot"]:
                for label, name in collections.items():
                    snapshots[label] = create_collection_snapshot(name)
            if options["prepare_aliases"]:
                replace_collection_alias(
                    alias_name=settings.QDRANT_CAD_MIGRATION_ALIAS,
                    collection_name=settings.QDRANT_CAD_COLLECTION_V2,
                )
                replace_collection_alias(
                    alias_name=settings.QDRANT_KNOWLEDGE_MIGRATION_ALIAS,
                    collection_name=settings.QDRANT_KNOWLEDGE_COLLECTION_V2,
                )
                alias_events.extend(
                    [
                        {"domain": "cad", "target": "v2"},
                        {"domain": "knowledge", "target": "v2"},
                    ]
                )
            if options["rollback_drill"]:
                for domain, alias, v1, v2 in (
                    (
                        "cad",
                        settings.QDRANT_CAD_MIGRATION_ALIAS,
                        settings.QDRANT_CAD_COLLECTION,
                        settings.QDRANT_CAD_COLLECTION_V2,
                    ),
                    (
                        "knowledge",
                        settings.QDRANT_KNOWLEDGE_MIGRATION_ALIAS,
                        settings.QDRANT_KNOWLEDGE_COLLECTION,
                        settings.QDRANT_KNOWLEDGE_COLLECTION_V2,
                    ),
                ):
                    replace_collection_alias(alias_name=alias, collection_name=v1)
                    alias_events.append({"domain": domain, "target": "v1-rollback"})
                    replace_collection_alias(alias_name=alias, collection_name=v2)
                    alias_events.append({"domain": domain, "target": "v2-restored"})
        else:
            checks["cad_qdrant_parity"] = True
            checks["knowledge_qdrant_parity"] = True

        passed = all(checks.values())
        payload = {
            "schema_version": "cpu-ai-release-gate@1.0",
            "passed": passed,
            "checks": checks,
            "counts": {
                "cad_expected": cad_expected,
                "cad_v2_ready": cad_ready,
                "knowledge_chunks_expected": knowledge_expected,
                "knowledge_chunks_v2_ready": knowledge_ready,
                "qdrant": qdrant_counts,
            },
            "aliases": alias_events,
            "snapshots": snapshots,
            "release_route": settings.CPU_AI_RELEASE_ROUTE,
            "rollback": "Set CPU_AI_RELEASE_ROUTE=v1 and restart application roles.",
            "environment": {
                "python": platform.python_version(),
                "processor": platform.processor() or platform.machine(),
                "gpu_required": False,
            },
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "quality_gate": {
                "status": "domain_approval_required",
                "reason": (
                    "Structural migration passing does not replace expert Golden QA approval."
                ),
            },
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))
        if not passed:
            failed = ", ".join(name for name, value in checks.items() if not value)
            raise CommandError(f"CPU AI release gate failed: {failed}")
