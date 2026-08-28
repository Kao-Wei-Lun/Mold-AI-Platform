from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q

from .cad_fixtures import AUTOMATED_CAD_SMOKE_DATASET, MANUAL_CAD_DATASET
from .models import (
    Artifact,
    ArtifactVersion,
    AuditEvent,
    CADModel,
    CAEComparison,
    CAEResult,
    CAERun,
    CAEStudy,
    CorrectiveAction,
    DefectObservation,
    FeatureSet,
    HMIExport,
    HMIExtractedField,
    HMIExtraction,
    Job,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSearch,
    LineageEdge,
    ProcessCaseSearch,
    ProcessParameter,
    ProcessRun,
    ReviewDecision,
    ReviewFinding,
    ReviewRun,
    SimilaritySearch,
    TrialCase,
)
from .vector_store import delete_feature_points, delete_named_points

OPERATIONS_RESET_CONFIRMATION = "RESET OPERATIONS"
DATASETS_RESET_CONFIRMATION = "RESET DATASETS"
REMOVABLE_DATASETS = {
    MANUAL_CAD_DATASET,
    AUTOMATED_CAD_SMOKE_DATASET,
    "public-demo-v1",
    "automated-smoke-v1",
}


class DemoResetError(RuntimeError):
    pass


@dataclass(frozen=True)
class DemoResetResult:
    dry_run: bool
    counts: dict[str, int]
    removed_storage_files: int
    removed_feature_points: int


def _target_artifacts():
    protected_preview_artifact_ids = (
        ArtifactVersion.objects.filter(preview_for_cad_models__isnull=False)
        .exclude(
            preview_for_cad_models__artifact_version__artifact__dataset_id__in=REMOVABLE_DATASETS
        )
        .values_list("artifact_id", flat=True)
    )
    return Artifact.objects.filter(
        Q(dataset_id__in=REMOVABLE_DATASETS)
        | Q(kind__in=[Artifact.Kind.HMI_SOURCE, Artifact.Kind.HMI_EXPORT])
    ).exclude(id__in=protected_preview_artifact_ids)


def reset_preview() -> dict[str, int]:
    artifacts = _target_artifacts()
    versions = ArtifactVersion.objects.filter(artifact__in=artifacts)
    reviews = ReviewRun.objects.exclude(job__idempotency_key__startswith="curated-cad:")
    return {
        "artifacts": artifacts.count(),
        "artifact_versions": versions.count(),
        "similarity_searches": SimilaritySearch.objects.count(),
        "design_reviews": reviews.count(),
        "knowledge_searches": KnowledgeSearch.objects.count(),
        "process_case_searches": ProcessCaseSearch.objects.count(),
        "cae_comparisons": CAEComparison.objects.count(),
        "hmi_extractions": HMIExtraction.objects.count(),
        "audit_events_preserved": AuditEvent.objects.count(),
    }


def reset_demo_operations(*, confirmation: str = "", dry_run: bool = True) -> DemoResetResult:
    counts = reset_preview()
    if dry_run:
        return DemoResetResult(True, counts, 0, 0)
    if confirmation != OPERATIONS_RESET_CONFIRMATION:
        raise DemoResetError(f"Confirmation must exactly equal {OPERATIONS_RESET_CONFIRMATION!r}.")

    target_artifact_ids = list(_target_artifacts().values_list("id", flat=True))
    target_versions = ArtifactVersion.objects.filter(artifact_id__in=target_artifact_ids)
    target_version_ids = list(target_versions.values_list("id", flat=True))
    storage_keys = list(target_versions.values_list("storage_key", flat=True))
    target_cad_models = CADModel.objects.filter(artifact_version_id__in=target_version_ids)
    target_feature_ids = [
        str(value)
        for value in FeatureSet.objects.filter(cad_model__in=target_cad_models).values_list(
            "id", flat=True
        )
    ]
    operational_reviews = ReviewRun.objects.exclude(job__idempotency_key__startswith="curated-cad:")
    review_job_ids = list(operational_reviews.values_list("job_id", flat=True))
    similarity_job_ids = list(SimilaritySearch.objects.values_list("job_id", flat=True))
    target_job_ids = (
        set(
            Job.objects.filter(input_artifact_version_id__in=target_version_ids).values_list(
                "id", flat=True
            )
        )
        | set(review_job_ids)
        | set(similarity_job_ids)
    )

    with transaction.atomic():
        ReviewDecision.objects.filter(finding__review_run__in=operational_reviews).delete()
        ReviewFinding.objects.filter(review_run__in=operational_reviews).delete()
        operational_reviews.delete()
        SimilaritySearch.objects.all().delete()
        KnowledgeSearch.objects.all().delete()
        ProcessCaseSearch.objects.all().delete()
        CAEComparison.objects.all().delete()

        HMIExport.objects.filter(
            Q(extraction__image_artifact_version_id__in=target_version_ids)
            | Q(artifact_version_id__in=target_version_ids)
        ).delete()
        HMIExtractedField.objects.filter(
            extraction__image_artifact_version_id__in=target_version_ids
        ).delete()
        HMIExtraction.objects.filter(image_artifact_version_id__in=target_version_ids).delete()

        target_documents = KnowledgeDocument.objects.filter(
            artifact_version_id__in=target_version_ids
        )
        KnowledgeChunk.objects.filter(document__in=target_documents).delete()
        target_documents.delete()

        LineageEdge.objects.filter(
            Q(from_artifact_version_id__in=target_version_ids)
            | Q(to_artifact_version_id__in=target_version_ids)
            | Q(job_id__in=target_job_ids)
        ).delete()
        FeatureSet.objects.filter(cad_model__in=target_cad_models).delete()
        target_cad_models.delete()
        Job.objects.filter(id__in=target_job_ids).delete()
        ArtifactVersion.objects.filter(id__in=target_version_ids).delete()
        Artifact.objects.filter(id__in=target_artifact_ids).delete()

        detail = {
            "schema_version": "1.0",
            "mode": "operations",
            "counts": counts,
            "audit_policy": "preserve_existing_and_append_reset_event",
        }
        AuditEvent.objects.create(
            event_type="demo.operations_reset.v1",
            actor_id="demo-operator",
            target_refs=["demo-scope:operations"],
            detail=detail,
            payload_hash=hashlib.sha256(
                json.dumps(detail, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )

    delete_feature_points(target_feature_ids)
    removed_files = 0
    for storage_key in storage_keys:
        if storage_key and default_storage.exists(storage_key):
            default_storage.delete(storage_key)
            removed_files += 1
    return DemoResetResult(False, counts, removed_files, len(target_feature_ids))


def datasets_reset_preview() -> dict[str, int]:
    """Return the exact canonical and operational record scope for a dataset reset."""
    return {
        "artifacts": Artifact.objects.count(),
        "artifact_versions": ArtifactVersion.objects.count(),
        "cad_models": CADModel.objects.count(),
        "feature_sets": FeatureSet.objects.count(),
        "jobs": Job.objects.count(),
        "similarity_searches": SimilaritySearch.objects.count(),
        "design_reviews": ReviewRun.objects.count(),
        "knowledge_documents": KnowledgeDocument.objects.count(),
        "knowledge_chunks": KnowledgeChunk.objects.count(),
        "knowledge_searches": KnowledgeSearch.objects.count(),
        "trial_cases": TrialCase.objects.count(),
        "process_runs": ProcessRun.objects.count(),
        "process_case_searches": ProcessCaseSearch.objects.count(),
        "cae_studies": CAEStudy.objects.count(),
        "cae_runs": CAERun.objects.count(),
        "cae_comparisons": CAEComparison.objects.count(),
        "hmi_extractions": HMIExtraction.objects.count(),
        "audit_events_preserved": AuditEvent.objects.count(),
    }


def reset_demo_datasets(*, confirmation: str = "", dry_run: bool = True) -> DemoResetResult:
    """Clear Demo records and indexes while preserving configuration and audit history.

    This deliberately does not delete profiles, rules, secrets, environment files, tunnel
    profiles, repositories, Docker volumes, or arbitrary filesystem paths. The caller must
    reseed the governed datasets after a confirmed reset.
    """
    counts = datasets_reset_preview()
    if dry_run:
        return DemoResetResult(True, counts, 0, 0)
    if confirmation != DATASETS_RESET_CONFIRMATION:
        raise DemoResetError(f"Confirmation must exactly equal {DATASETS_RESET_CONFIRMATION!r}.")

    storage_keys = list(ArtifactVersion.objects.values_list("storage_key", flat=True))
    feature_ids = [str(value) for value in FeatureSet.objects.values_list("id", flat=True)]
    knowledge_chunk_ids = [
        str(value) for value in KnowledgeChunk.objects.values_list("id", flat=True)
    ]

    # Delete vectors before canonical records. If Qdrant is unavailable, fail closed while
    # PostgreSQL and artifact storage remain intact and recoverable.
    delete_feature_points(feature_ids)
    delete_named_points(
        collection_name=settings.QDRANT_KNOWLEDGE_COLLECTION,
        point_ids=knowledge_chunk_ids,
    )

    with transaction.atomic():
        ReviewDecision.objects.all().delete()
        ReviewFinding.objects.all().delete()
        ReviewRun.objects.all().delete()
        SimilaritySearch.objects.all().delete()
        KnowledgeSearch.objects.all().delete()
        ProcessCaseSearch.objects.all().delete()
        CAEComparison.objects.all().delete()

        HMIExport.objects.all().delete()
        HMIExtractedField.objects.all().delete()
        HMIExtraction.objects.all().delete()

        KnowledgeChunk.objects.all().delete()
        KnowledgeDocument.objects.all().delete()

        CorrectiveAction.objects.all().delete()
        DefectObservation.objects.all().delete()
        ProcessParameter.objects.all().delete()
        ProcessRun.objects.all().delete()
        TrialCase.objects.all().delete()

        CAEResult.objects.all().delete()
        CAERun.objects.all().delete()
        CAEStudy.objects.all().delete()

        LineageEdge.objects.all().delete()
        FeatureSet.objects.all().delete()
        CADModel.objects.all().delete()
        Job.objects.all().delete()
        ArtifactVersion.objects.all().delete()
        Artifact.objects.all().delete()

        detail = {
            "schema_version": "1.0",
            "mode": "datasets",
            "counts": counts,
            "audit_policy": "preserve_existing_and_append_reset_event",
            "preserved_configuration": [
                "similarity_profiles",
                "rule_profiles_and_versions",
                "environment_and_tunnel_configuration",
            ],
        }
        AuditEvent.objects.create(
            event_type="demo.datasets_reset.v1",
            actor_id="demo-operator",
            target_refs=["demo-scope:datasets"],
            detail=detail,
            payload_hash=hashlib.sha256(
                json.dumps(detail, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )

    removed_files = 0
    for storage_key in storage_keys:
        if storage_key and default_storage.exists(storage_key):
            default_storage.delete(storage_key)
            removed_files += 1
    return DemoResetResult(
        False,
        counts,
        removed_files,
        len(feature_ids) + len(knowledge_chunk_ids),
    )
