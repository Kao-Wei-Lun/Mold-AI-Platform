from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from celery import current_app
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    AuditEvent,
    BulkImportBatch,
    CADModel,
    Job,
    JobEvent,
    KnowledgeDocument,
    ReviewRun,
)
from .tasks import update_job

TASK_NAMES = {
    "cad.parse": "platform_core.process_cad_job",
    "knowledge.ingest": "platform_core.process_knowledge_job",
    "mold.design_review": "platform_core.run_design_review_job",
    "mold.similarity_search": "platform_core.run_similarity_job",
    "data.ingestion.commit": "platform_core.commit_ingestion_job",
}


def _task_args(job: Job) -> list[str]:
    if job.capability_id == "data.ingestion.commit":
        batch = BulkImportBatch.objects.filter(job=job).first()
        if batch is None:
            return [str(job.id), "", "recovery"]
        return [str(job.id), str(batch.id), batch.created_by]
    return [str(job.id)]


def _stale_jobs(cutoff, limit: int):
    running_stale = Q(state=Job.State.RUNNING) & (
        Q(heartbeat_at__lt=cutoff)
        | Q(heartbeat_at__isnull=True, started_at__lt=cutoff)
        | Q(heartbeat_at__isnull=True, started_at__isnull=True, created_at__lt=cutoff)
    )
    queued_stale = Q(state=Job.State.QUEUED, created_at__lt=cutoff)
    return Job.objects.filter(queued_stale | running_stale).order_by("created_at")[:limit]


def _is_stale(job: Job, cutoff) -> bool:
    if job.state == Job.State.QUEUED:
        return job.created_at < cutoff
    if job.state != Job.State.RUNNING:
        return False
    activity_at = job.heartbeat_at or job.started_at or job.created_at
    return activity_at < cutoff


def stale_job_snapshot(*, stale_minutes: int = 15, limit: int = 100) -> dict[str, object]:
    cutoff = timezone.now() - timedelta(minutes=stale_minutes)
    jobs = list(_stale_jobs(cutoff, limit))
    return {
        "schema_version": "1.0",
        "policy": {
            "stale_minutes": stale_minutes,
            "limit": limit,
            "queued": "requeue_when_supported",
            "running": "requeue_below_max_attempts_else_fail",
        },
        "counts": {
            "total": len(jobs),
            "queued": sum(job.state == Job.State.QUEUED for job in jobs),
            "running": sum(job.state == Job.State.RUNNING for job in jobs),
            "retryable": sum(
                job.capability_id in TASK_NAMES
                and (job.state == Job.State.QUEUED or job.attempt < job.max_attempts)
                for job in jobs
            ),
        },
    }


def _synchronize_failed_domain(job: Job, error_code: str) -> None:
    if job.capability_id == "cad.parse":
        CADModel.objects.filter(artifact_version_id=job.input_artifact_version_id).update(
            geometry_status=CADModel.GeometryStatus.FAILED,
            error_code=error_code,
        )
    elif job.capability_id == "knowledge.ingest":
        KnowledgeDocument.objects.filter(artifact_version_id=job.input_artifact_version_id).update(
            ingestion_status=KnowledgeDocument.IngestionStatus.FAILED,
            error_code=error_code,
        )
    elif job.capability_id == "mold.design_review":
        ReviewRun.objects.filter(job_id=job.id).update(review_status=ReviewRun.Status.FAILED)
    elif job.capability_id == "data.ingestion.commit":
        BulkImportBatch.objects.filter(job_id=job.id).update(status=BulkImportBatch.Status.FAILED)


def _fail_job(job: Job, code: str, message: str) -> None:
    _synchronize_failed_domain(job, code)
    update_job(
        job.id,
        state=Job.State.FAILED,
        stage="recovery_failed",
        progress=100,
        error_code=code,
        error_message=message,
    )


def _requeue_job(job: Job) -> None:
    previous_state = job.state
    job.state = Job.State.QUEUED
    job.stage = "recovery_requeued"
    job.progress = 0
    job.started_at = None
    job.heartbeat_at = None
    job.completed_at = None
    job.error_code = ""
    job.error_message = ""
    job.save(
        update_fields=[
            "state",
            "stage",
            "progress",
            "started_at",
            "heartbeat_at",
            "completed_at",
            "error_code",
            "error_message",
        ]
    )
    JobEvent.objects.create(
        job=job,
        from_state=previous_state,
        to_state=Job.State.QUEUED,
        stage="recovery_requeued",
        progress=0,
        detail={"reason_code": "STALE_JOB_RECOVERY"},
    )


def recover_stale_jobs(
    *, stale_minutes: int = 15, limit: int = 100, apply: bool = False
) -> dict[str, object]:
    snapshot = stale_job_snapshot(stale_minutes=stale_minutes, limit=limit)
    if not apply:
        return {**snapshot, "dry_run": True, "actions": {"requeued": 0, "failed": 0}}

    cutoff = timezone.now() - timedelta(minutes=stale_minutes)
    candidate_ids = list(_stale_jobs(cutoff, limit).values_list("id", flat=True))
    actions = {"requeued": 0, "failed": 0, "queue_failures": 0, "skipped_changed": 0}

    for job_id in candidate_ids:
        task_name = ""
        queue = ""
        with transaction.atomic():
            job = Job.objects.select_for_update().get(pk=job_id)
            if not _is_stale(job, cutoff):
                actions["skipped_changed"] += 1
                continue
            task_name = TASK_NAMES.get(job.capability_id, "")
            queue = job.queue
            if not task_name:
                _fail_job(
                    job,
                    "STALE_JOB_UNSUPPORTED_CAPABILITY",
                    "The stale job capability has no approved recovery task mapping.",
                )
                actions["failed"] += 1
                continue
            if job.state == Job.State.RUNNING and job.attempt >= job.max_attempts:
                _fail_job(
                    job,
                    "JOB_HEARTBEAT_EXPIRED",
                    "The running job heartbeat expired after its permitted attempts.",
                )
                actions["failed"] += 1
                continue
            _requeue_job(job)

        try:
            current_app.send_task(task_name, args=_task_args(job), queue=queue)
            actions["requeued"] += 1
        except Exception:
            with transaction.atomic():
                job = Job.objects.select_for_update().get(pk=job_id)
                _fail_job(
                    job,
                    "JOB_RECOVERY_QUEUE_UNAVAILABLE",
                    "The stale job was recovered but could not be submitted to its queue.",
                )
            actions["failed"] += 1
            actions["queue_failures"] += 1

    detail = {
        "schema_version": "1.0",
        "policy": snapshot["policy"],
        "candidate_counts": snapshot["counts"],
        "actions": actions,
    }
    AuditEvent.objects.create(
        event_type="demo.stale_job_recovery.v1",
        actor_id="demo-operator",
        target_refs=["demo-scope:jobs"],
        detail=detail,
        payload_hash=hashlib.sha256(
            json.dumps(detail, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )
    return {**snapshot, "dry_run": False, "actions": actions}
