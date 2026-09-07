from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from platform_core.cad_similarity_v2 import extract_and_index_cad_model_v2
from platform_core.models import CADModel, FeatureSet


class Command(BaseCommand):
    help = "Validate or idempotently populate the CPU CAD similarity v2 shadow index."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Write missing or failed v2 feature sets. "
                "Without this flag the command is read-only."
            ),
        )
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options) -> None:
        queryset = CADModel.objects.filter(
            geometry_status=CADModel.GeometryStatus.SUCCEEDED,
            preview_artifact_version__isnull=False,
        ).order_by("created_at")
        if options["limit"] > 0:
            queryset = queryset[: options["limit"]]

        inspected = indexed = ready = 0
        failures: list[dict[str, str]] = []
        for cad_model in queryset.iterator():
            inspected += 1
            existing = cad_model.feature_sets.filter(
                feature_type="cad_similarity",
                schema_version="2.0",
                extractor_version="2.1.0",
                index_status=FeatureSet.IndexStatus.INDEXED,
            ).first()
            if existing:
                ready += 1
                continue
            if not options["apply"]:
                continue
            try:
                extract_and_index_cad_model_v2(cad_model)
                indexed += 1
                ready += 1
            except Exception as exc:  # command must report every failed record
                failures.append(
                    {
                        "cad_model_id": str(cad_model.id),
                        "code": str(getattr(exc, "code", "CAD_V2_MIGRATION_FAILED")),
                    }
                )

        payload = {
            "schema_version": "cad-index-migration@1.0",
            "mode": "apply" if options["apply"] else "validate",
            "inspected": inspected,
            "ready": ready,
            "indexed": indexed,
            "missing": inspected - ready,
            "failures": failures,
            "activation_changed": False,
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))
        if failures:
            raise CommandError(f"CAD v2 migration failed for {len(failures)} record(s).")
