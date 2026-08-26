import hashlib
import uuid
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from .cad_processing import CADProcessingError, parse_cad_file
from .design_review import DesignReviewValidationError, evaluate_review
from .models import Artifact, ArtifactVersion, CADModel, Job, JobEvent, LineageEdge, ReviewRun
from .similarity import SimilarityValidationError, extract_and_index_cad_model, run_similarity
from .vector_store import VectorStoreError

PREVIEW_NAMESPACE = uuid.UUID("732b7e1e-3c42-4af1-a4ec-e0c11fdf0d58")
TERMINAL_STATES = {Job.State.SUCCEEDED, Job.State.FAILED, Job.State.CANCELLED, Job.State.EXPIRED}


@shared_task(name="platform_core.echo")
def echo(payload: object) -> object:
    return payload


def update_job(
    job_id: str | uuid.UUID,
    *,
    state: str | None = None,
    stage: str,
    progress: int,
    result_ref: str = "",
    error_code: str = "",
    error_message: str = "",
) -> Job:
    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        previous_state = job.state
        next_state = state or job.state
        next_progress = max(job.progress, min(progress, 100))
        now = timezone.now()

        if previous_state in TERMINAL_STATES and next_state != previous_state:
            return job

        if next_state == Job.State.RUNNING and job.started_at is None:
            job.started_at = now
            job.attempt += 1
        if next_state == Job.State.RUNNING:
            job.heartbeat_at = now
        if next_state in TERMINAL_STATES:
            job.completed_at = now

        job.state = next_state
        job.stage = stage
        job.progress = next_progress
        if result_ref:
            job.result_ref = result_ref
        job.error_code = error_code
        job.error_message = error_message[:512]
        job.save()
        JobEvent.objects.create(
            job=job,
            from_state=previous_state,
            to_state=next_state,
            stage=stage,
            progress=next_progress,
            detail={"error_code": error_code} if error_code else {},
        )
        return job


def mark_job_failed(job_id: str | uuid.UUID, code: str, message: str) -> Job:
    CADModel.objects.filter(artifact_version__input_jobs__id=job_id).update(
        geometry_status=CADModel.GeometryStatus.FAILED,
        error_code=code,
    )
    return update_job(
        job_id,
        state=Job.State.FAILED,
        stage="failed",
        progress=100,
        error_code=code,
        error_message=message,
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _persist_preview(
    job: Job, source_version: ArtifactVersion, preview_path: Path
) -> ArtifactVersion:
    artifact_id = uuid.uuid5(PREVIEW_NAMESPACE, f"{source_version.id}:artifact")
    version_id = uuid.uuid5(PREVIEW_NAMESPACE, f"{source_version.id}:version")
    storage_key = f"derived/{artifact_id}/{version_id}/preview.stl"
    preview_sha256 = _file_sha256(preview_path)

    artifact, _ = Artifact.objects.get_or_create(
        id=artifact_id,
        defaults={
            "name": f"{source_version.artifact.name} preview",
            "kind": Artifact.Kind.CAD_PREVIEW,
            "classification": source_version.classification,
            "created_by": "cad-worker",
        },
    )

    existing_version = ArtifactVersion.objects.filter(pk=version_id).first()
    if existing_version:
        return existing_version

    if default_storage.exists(storage_key):
        default_storage.delete(storage_key)
    with preview_path.open("rb") as preview_file:
        saved_key = default_storage.save(storage_key, File(preview_file))
    if saved_key != storage_key:
        raise RuntimeError("The deterministic preview storage key already exists.")

    try:
        with transaction.atomic():
            preview_version = ArtifactVersion.objects.create(
                id=version_id,
                artifact=artifact,
                version_number=1,
                original_filename=f"{Path(source_version.original_filename).stem}.preview.stl",
                media_type="model/stl",
                format="stl",
                size_bytes=preview_path.stat().st_size,
                sha256=preview_sha256,
                storage_key=storage_key,
                source_system="cad-worker",
                classification=source_version.classification,
                malware_status=ArtifactVersion.MalwareStatus.BASIC_SCREENED,
            )
            LineageEdge.objects.create(
                from_artifact_version=source_version,
                to_artifact_version=preview_version,
                relationship=LineageEdge.Relationship.DERIVED_FROM,
                job=job,
            )
            return preview_version
    except Exception:
        default_storage.delete(storage_key)
        raise


@shared_task(name="platform_core.process_cad_job")
def process_cad_job(job_id: str) -> dict[str, str]:
    job = Job.objects.select_related("input_artifact_version__artifact").get(pk=job_id)
    if job.state in TERMINAL_STATES:
        terminal_result = {"job_id": str(job.id), "state": job.state}
        if job.result_ref:
            terminal_result["result_ref"] = job.result_ref
        if job.error_code:
            terminal_result["error_code"] = job.error_code
        return terminal_result

    source_version = job.input_artifact_version
    cad_model = source_version.cad_model
    temporary_preview = Path(settings.MEDIA_ROOT) / "tmp" / f"{job.id}.stl"

    try:
        update_job(job.id, state=Job.State.RUNNING, stage="validating", progress=10)
        cad_model.geometry_status = CADModel.GeometryStatus.RUNNING
        cad_model.error_code = ""
        cad_model.save(update_fields=["geometry_status", "error_code", "updated_at"])

        update_job(job.id, stage="parsing_geometry", progress=30)
        source_path = Path(default_storage.path(source_version.storage_key))
        parse_result = parse_cad_file(source_path, source_version.format, temporary_preview)

        update_job(job.id, stage="creating_preview", progress=75)
        preview_version = _persist_preview(job, source_version, temporary_preview)

        cad_model.unit_system = parse_result.unit_system
        cad_model.parser_name = parse_result.parser_name
        cad_model.parser_version = parse_result.parser_version
        cad_model.geometry_status = CADModel.GeometryStatus.SUCCEEDED
        cad_model.bounding_box = parse_result.bounding_box
        cad_model.volume = parse_result.volume
        cad_model.surface_area = parse_result.surface_area
        cad_model.face_count = parse_result.face_count
        cad_model.edge_count = parse_result.edge_count
        cad_model.surface_type_histogram = parse_result.surface_type_histogram
        cad_model.quality_flags = parse_result.quality_flags
        cad_model.preview_artifact_version = preview_version
        cad_model.error_code = ""
        cad_model.save()

        if settings.SIMILARITY_AUTO_INDEX:
            update_job(job.id, stage="extracting_similarity_features", progress=82)
            try:
                extract_and_index_cad_model(cad_model)
                update_job(job.id, stage="similarity_features_indexed", progress=92)
            except VectorStoreError:
                quality_flags = list(cad_model.quality_flags)
                if "SIMILARITY_INDEX_UNAVAILABLE" not in quality_flags:
                    quality_flags.append("SIMILARITY_INDEX_UNAVAILABLE")
                    cad_model.quality_flags = quality_flags
                    cad_model.save(update_fields=["quality_flags", "updated_at"])
                update_job(job.id, stage="similarity_index_degraded", progress=92)

        result_ref = f"cad_model:{cad_model.id}"
        update_job(
            job.id,
            state=Job.State.SUCCEEDED,
            stage="completed",
            progress=100,
            result_ref=result_ref,
        )
        return {"job_id": str(job.id), "state": Job.State.SUCCEEDED, "result_ref": result_ref}
    except CADProcessingError as exc:
        mark_job_failed(job.id, exc.code, exc.user_message)
        return {"job_id": str(job.id), "state": Job.State.FAILED, "error_code": exc.code}
    except Exception:
        mark_job_failed(
            job.id,
            "INTERNAL_CAD_PROCESSING",
            "The CAD processing job failed unexpectedly. Use the correlation ID for support.",
        )
        raise
    finally:
        temporary_preview.unlink(missing_ok=True)


@shared_task(name="platform_core.run_similarity_job")
def run_similarity_job(job_id: str) -> dict[str, str]:
    job = Job.objects.select_related(
        "similarity_search__query_feature_set__cad_model__artifact_version__artifact",
        "similarity_search__profile",
    ).get(pk=job_id)
    if job.state in TERMINAL_STATES:
        terminal_result = {"job_id": str(job.id), "state": job.state}
        if job.result_ref:
            terminal_result["result_ref"] = job.result_ref
        if job.error_code:
            terminal_result["error_code"] = job.error_code
        return terminal_result

    try:
        update_job(job.id, state=Job.State.RUNNING, stage="retrieving_candidates", progress=20)
        result = run_similarity(job.similarity_search)
        update_job(job.id, stage="persisting_ranked_results", progress=85)
        search = job.similarity_search
        search.result = result
        search.completed_at = timezone.now()
        search.save(update_fields=["result", "completed_at"])
        result_ref = f"similarity_search:{search.id}"
        update_job(
            job.id,
            state=Job.State.SUCCEEDED,
            stage="completed",
            progress=100,
            result_ref=result_ref,
        )
        return {"job_id": str(job.id), "state": Job.State.SUCCEEDED, "result_ref": result_ref}
    except (SimilarityValidationError, VectorStoreError) as exc:
        update_job(
            job.id,
            state=Job.State.FAILED,
            stage="failed",
            progress=100,
            error_code=exc.code,
            error_message=exc.user_message,
        )
        return {"job_id": str(job.id), "state": Job.State.FAILED, "error_code": exc.code}
    except Exception:
        update_job(
            job.id,
            state=Job.State.FAILED,
            stage="failed",
            progress=100,
            error_code="INTERNAL_SIMILARITY_SEARCH",
            error_message=(
                "The similarity search failed unexpectedly. Use the correlation ID for support."
            ),
        )
        raise


@shared_task(name="platform_core.run_design_review_job")
def run_design_review_job(job_id: str) -> dict[str, str]:
    job = Job.objects.select_related(
        "design_review__cad_model__artifact_version",
        "design_review__profile",
    ).get(pk=job_id)
    if job.state in TERMINAL_STATES:
        terminal_result = {"job_id": str(job.id), "state": job.state}
        if job.result_ref:
            terminal_result["result_ref"] = job.result_ref
        if job.error_code:
            terminal_result["error_code"] = job.error_code
        return terminal_result

    review = job.design_review
    try:
        update_job(job.id, state=Job.State.RUNNING, stage="loading_rule_snapshot", progress=15)
        review.review_status = ReviewRun.Status.RUNNING
        review.save(update_fields=["review_status"])
        update_job(job.id, stage="evaluating_deterministic_rules", progress=45)
        evaluate_review(review)
        update_job(job.id, stage="persisting_review_evidence", progress=85)
        result_ref = f"design_review:{review.id}"
        update_job(
            job.id,
            state=Job.State.SUCCEEDED,
            stage="completed",
            progress=100,
            result_ref=result_ref,
        )
        return {"job_id": str(job.id), "state": Job.State.SUCCEEDED, "result_ref": result_ref}
    except DesignReviewValidationError as exc:
        review.review_status = ReviewRun.Status.FAILED
        review.save(update_fields=["review_status"])
        update_job(
            job.id,
            state=Job.State.FAILED,
            stage="failed",
            progress=100,
            error_code=exc.code,
            error_message=exc.user_message,
        )
        return {"job_id": str(job.id), "state": Job.State.FAILED, "error_code": exc.code}
    except Exception:
        review.review_status = ReviewRun.Status.FAILED
        review.save(update_fields=["review_status"])
        update_job(
            job.id,
            state=Job.State.FAILED,
            stage="failed",
            progress=100,
            error_code="INTERNAL_DESIGN_REVIEW",
            error_message=(
                "The design review failed unexpectedly. Use the correlation ID for support."
            ),
        )
        raise
