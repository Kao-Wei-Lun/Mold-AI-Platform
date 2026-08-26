from .models import Artifact, ArtifactVersion, CADModel, Job, SimilaritySearch


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
    for version in versions:
        jobs.extend(job_payload(job) for job in version.input_jobs.all())
    return {
        "artifact_id": str(artifact.id),
        "name": artifact.name,
        "kind": artifact.kind,
        "classification": artifact.classification,
        "dataset_id": artifact.dataset_id,
        "product_type": artifact.product_type,
        "material_code": artifact.material_code,
        "created_at": artifact.created_at.isoformat(),
        "versions": [artifact_version_payload(version) for version in versions],
        "jobs": jobs,
    }
