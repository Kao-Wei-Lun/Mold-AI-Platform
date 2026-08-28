from __future__ import annotations

from django.conf import settings
from django.db import connection
from django.db.models import Count
from django.utils import timezone

from .assistant_providers import get_assistant_provider
from .cad_fixtures import curated_cad_status
from .design_review import get_demo_rule_profile
from .health import collect_readiness
from .job_recovery import stale_job_snapshot
from .models import (
    Artifact,
    ArtifactVersion,
    CAEStudy,
    FeatureSet,
    HMIExtraction,
    Job,
    KnowledgeDocument,
    TrialCase,
)

OPERATIONS_CONTRACT_VERSION = "1.0"


def release_snapshot_payload() -> dict[str, object]:
    profile = get_demo_rule_profile()
    artifact_versions = ArtifactVersion.objects.select_related("artifact").order_by(
        "artifact__dataset_id", "artifact_id", "version_number"
    )
    datasets = {
        item["dataset_id"]: item["count"]
        for item in Artifact.objects.values("dataset_id")
        .order_by("dataset_id")
        .annotate(count=Count("id"))
    }
    feature_indexes = list(
        FeatureSet.objects.values("index_collection", "index_version", "index_status")
        .order_by("index_collection", "index_version", "index_status")
        .annotate(count=Count("id"))
    )
    return {
        "schema_version": "1.0",
        "operations_contract_version": OPERATIONS_CONTRACT_VERSION,
        "created_at": timezone.now().isoformat(),
        "application": {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
        },
        "database": {"vendor": connection.vendor},
        "readiness": collect_readiness(),
        "datasets": {
            "artifact_counts": datasets,
            "curated_cad": curated_cad_status(),
            "indexed_knowledge_documents": KnowledgeDocument.objects.filter(
                ingestion_status=KnowledgeDocument.IngestionStatus.INDEXED
            ).count(),
            "process_trial_cases": TrialCase.objects.count(),
            "cae_studies": CAEStudy.objects.count(),
            "hmi_extractions": HMIExtraction.objects.count(),
        },
        "profiles": {
            "design_review": {
                "profile_key": profile.profile_key,
                "version": profile.version,
                "ruleset_checksum": profile.ruleset_checksum,
                "rule_count": profile.rules.filter(enabled=True).count(),
            },
            "similarity": {
                "profile_key": "demo-general@1.0",
                "feature_schema_version": "1.0",
                "index_version": settings.SIMILARITY_INDEX_VERSION,
            },
        },
        "indexes": feature_indexes,
        "records": {
            "artifacts": Artifact.objects.count(),
            "artifact_versions": artifact_versions.count(),
            "jobs": Job.objects.count(),
        },
        "job_recovery": stale_job_snapshot(),
        "artifact_manifest": [
            {
                "artifact_id": str(version.artifact_id),
                "artifact_version_id": str(version.id),
                "dataset_id": version.artifact.dataset_id,
                "kind": version.artifact.kind,
                "version_number": version.version_number,
                "format": version.format,
                "size_bytes": version.size_bytes,
                "sha256": version.sha256,
                "storage_key": version.storage_key,
                "source_system": version.source_system,
                "classification": version.classification,
            }
            for version in artifact_versions
        ],
        "assistant_provider": get_assistant_provider().health().payload(),
        "excluded_sensitive_material": [
            "environment_files",
            "api_keys",
            "demo_bearer_token",
            "tunnel_runtime_key",
            "browser_session_storage",
        ],
    }
