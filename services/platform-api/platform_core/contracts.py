from .knowledge import knowledge_document_payload
from .models import (
    Artifact,
    ArtifactVersion,
    CADModel,
    Job,
    KnowledgeDocument,
    ReviewDecision,
    ReviewFinding,
    ReviewRun,
    RuleProfile,
    RuleVersion,
    SimilaritySearch,
)


def artifact_version_payload(version: ArtifactVersion) -> dict[str, object]:
    return {
        "artifact_version_id": str(version.id),
        "version_number": version.version_number,
        "original_filename": version.original_filename,
        "media_type": version.media_type,
        "format": version.format,
        "size_bytes": version.size_bytes,
        "sha256": version.sha256,
        "classification": version.classification,
        "malware_status": version.malware_status,
        "created_at": version.created_at.isoformat(),
        "download_url": f"/api/v1/artifact-versions/{version.id}/download",
    }


def cad_model_payload(cad_model: CADModel) -> dict[str, object]:
    preview = None
    if cad_model.preview_artifact_version_id:
        preview = artifact_version_payload(cad_model.preview_artifact_version)
    feature_set = cad_model.feature_sets.order_by("-created_at").first()
    similarity_index = None
    if feature_set:
        similarity_index = {
            "feature_set_id": str(feature_set.id),
            "schema_version": feature_set.schema_version,
            "extractor_version": feature_set.extractor_version,
            "index_version": feature_set.index_version,
            "status": feature_set.index_status,
            "error_code": feature_set.index_error_code or None,
        }
    return {
        "cad_model_id": str(cad_model.id),
        "artifact_version_id": str(cad_model.artifact_version_id),
        "cad_format": cad_model.cad_format,
        "unit_system": cad_model.unit_system,
        "parser": {
            "name": cad_model.parser_name,
            "version": cad_model.parser_version,
        },
        "geometry_status": cad_model.geometry_status,
        "bounding_box": cad_model.bounding_box,
        "volume": cad_model.volume,
        "surface_area": cad_model.surface_area,
        "face_count": cad_model.face_count,
        "edge_count": cad_model.edge_count,
        "surface_type_histogram": cad_model.surface_type_histogram,
        "quality_flags": cad_model.quality_flags,
        "preview": preview,
        "similarity_index": similarity_index,
    }


def job_payload(job: Job) -> dict[str, object]:
    result = None
    if job.state == Job.State.SUCCEEDED and job.capability_id == "cad.parse":
        try:
            cad_model = job.input_artifact_version.cad_model
            result = cad_model_payload(cad_model)
        except CADModel.DoesNotExist:
            pass
    elif job.state == Job.State.SUCCEEDED and job.capability_id == "mold.similarity_search":
        try:
            result = job.similarity_search.result
        except SimilaritySearch.DoesNotExist:
            pass
    elif job.state == Job.State.SUCCEEDED and job.capability_id == "mold.design_review":
        try:
            result = review_payload(job.design_review)
        except ReviewRun.DoesNotExist:
            pass
    elif job.state == Job.State.SUCCEEDED and job.capability_id == "knowledge.ingest":
        try:
            result = knowledge_document_payload(job.input_artifact_version.knowledge_document)
        except KnowledgeDocument.DoesNotExist:
            pass

    error = None
    if job.error_code:
        error = {
            "code": job.error_code,
            "message": job.error_message,
            "retryable": False,
            "correlation_id": str(job.correlation_id),
        }

    return {
        "schema_version": "1.0",
        "job_id": str(job.id),
        "capability": f"{job.capability_id}@{job.capability_version}",
        "state": job.state,
        "stage": job.stage,
        "progress": job.progress,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "queue": job.queue,
        "resource_class": job.resource_class,
        "artifact_version_id": str(job.input_artifact_version_id),
        "result_ref": job.result_ref or None,
        "result": result,
        "error": error,
        "correlation_id": str(job.correlation_id),
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def artifact_payload(artifact: Artifact) -> dict[str, object]:
    versions = list(artifact.versions.all())
    jobs = []
    source: dict[str, object] | None = None
    for version in versions:
        for job in version.input_jobs.all():
            jobs.append(job_payload(job))
            if job.capability_id == "cad.parse" and isinstance(job.input_snapshot, dict):
                candidate = job.input_snapshot.get("source")
                if isinstance(candidate, dict):
                    source = candidate
    return {
        "artifact_id": str(artifact.id),
        "name": artifact.name,
        "kind": artifact.kind,
        "classification": artifact.classification,
        "dataset_id": artifact.dataset_id,
        "product_type": artifact.product_type,
        "material_code": artifact.material_code,
        "mold_revision_id": (str(artifact.mold_revision_id) if artifact.mold_revision_id else None),
        "mold_revision": (
            {
                "revision_code": artifact.mold_revision.revision_code,
                "mold_id": str(artifact.mold_revision.mold_id),
                "mold_code": artifact.mold_revision.mold.mold_code,
            }
            if artifact.mold_revision_id
            else None
        ),
        "lifecycle_status": artifact.lifecycle_status,
        "quality_status": artifact.quality_status,
        "created_at": artifact.created_at.isoformat(),
        "source": source,
        "versions": [artifact_version_payload(version) for version in versions],
        "jobs": jobs,
    }


def rule_payload(rule: RuleVersion) -> dict[str, object]:
    return {
        "rule_version_id": str(rule.id),
        "rule_id": rule.rule_id,
        "rule_version": rule.rule_version,
        "title": rule.title,
        "description": rule.description,
        "evaluator": rule.evaluator,
        "applicability": rule.applicability,
        "measurement_definition": rule.parameters,
        "condition": {
            "operator": rule.operator,
            "limit": rule.limit_value,
            "unit": rule.unit,
            "tolerance": rule.tolerance,
        },
        "severity": rule.severity,
        "risk_type": rule.risk_type,
        "recommendation": rule.recommendation,
        "reference": rule.reference,
        "enabled": rule.enabled,
    }


def rule_profile_payload(profile: RuleProfile, *, include_rules: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        "profile_id": str(profile.id),
        "profile_key": profile.profile_key,
        "version": profile.version,
        "status": profile.status,
        "workflow_status": profile.workflow_status,
        "change_summary": profile.change_summary,
        "row_version": profile.row_version,
        "owner": profile.owner,
        "submitted_by": profile.submitted_by or None,
        "reviewed_by": profile.reviewed_by or None,
        "approved_by": profile.approved_by,
        "published_at": profile.published_at.isoformat() if profile.published_at else None,
        "retired_at": profile.retired_at.isoformat() if profile.retired_at else None,
        "ruleset_checksum": profile.ruleset_checksum,
        "rule_count": profile.rules.filter(enabled=True).count(),
    }
    if include_rules:
        payload["rules"] = [rule_payload(rule) for rule in profile.rules.filter(enabled=True)]
    return payload


def review_decision_payload(decision: ReviewDecision) -> dict[str, object]:
    return {
        "decision_id": str(decision.id),
        "decision": decision.decision,
        "reason": decision.reason,
        "decided_by": decision.decided_by,
        "approved_by": decision.approved_by or None,
        "created_at": decision.created_at.isoformat(),
    }


def review_finding_payload(finding: ReviewFinding) -> dict[str, object]:
    return {
        "finding_id": str(finding.id),
        "rule": rule_payload(finding.rule_version),
        "result": finding.result,
        "actual_value": finding.actual_value,
        "limit_value": finding.limit_value,
        "unit": finding.unit,
        "severity": finding.severity,
        "risk_type": finding.risk_type,
        "geometry_location": finding.geometry_location,
        "evidence_refs": finding.evidence_refs,
        "quality_flags": finding.quality_flags,
        "message": finding.message,
        "decisions": [review_decision_payload(item) for item in finding.decisions.all()],
    }


def review_payload(review: ReviewRun) -> dict[str, object]:
    cad_model = review.cad_model
    preview = None
    if cad_model.preview_artifact_version_id:
        preview = artifact_version_payload(cad_model.preview_artifact_version)
    return {
        "review_id": str(review.id),
        "job_id": str(review.job_id),
        "review_status": review.review_status,
        "artifact_version_id": str(cad_model.artifact_version_id),
        "profile": rule_profile_payload(review.profile, include_rules=False),
        "geometry_engine_version": review.geometry_engine_version,
        "input_snapshot": review.input_snapshot,
        "context": review.context,
        "summary": review.result_summary,
        "preview": preview,
        "findings": [review_finding_payload(item) for item in review.findings.all()],
        "created_at": review.created_at.isoformat(),
        "completed_at": review.completed_at.isoformat() if review.completed_at else None,
        "limitations": [
            "This Demo profile contains synthetic thresholds and is not "
            "production engineering guidance.",
            "Rib and draft checks use explicitly supplied Demo measurements; "
            "automatic local face measurement is future scope.",
            "Review decisions do not modify the immutable deterministic finding result.",
        ],
    }
