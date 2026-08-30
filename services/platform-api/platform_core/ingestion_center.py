from __future__ import annotations

import hashlib
import json
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from .identity import audit_identity_event
from .ingestion_adapters import CommitResult, commit_record, validate_records
from .master_data import invalidate_master_data_cache
from .models import (
    Artifact,
    ArtifactVersion,
    BulkImportBatch,
    IngestionIssue,
    IngestionRecordResult,
    IngestionSourceFile,
    MasterDataItem,
    ReconciliationReport,
)

EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"


class IngestionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


def attach_source_bytes(
    batch: BulkImportBatch,
    *,
    file_name: str,
    content: bytes,
    mime_type: str,
    source_system: str = "manual_upload",
) -> ArtifactVersion:
    safe_name = file_name.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
    if not safe_name or safe_name in {".", ".."}:
        raise IngestionError("VALIDATION_FILENAME", "A valid source filename is required.")
    if not content:
        raise IngestionError("VALIDATION_EMPTY_FILE", "The source file is empty.")
    if EICAR_MARKER in content:
        raise IngestionError(
            "VALIDATION_MALWARE_TEST_SIGNATURE",
            "The source contains a malware test signature and was rejected.",
        )
    digest = hashlib.sha256(content).hexdigest()
    artifact_id = uuid.uuid4()
    version_id = uuid.uuid4()
    suffix = safe_name.rsplit(".", maxsplit=1)[-1].lower() if "." in safe_name else "bin"
    storage_key = f"ingestion/{batch.id}/{artifact_id}/{version_id}/source.{suffix}"
    stored = False
    try:
        with transaction.atomic():
            artifact = Artifact.objects.create(
                id=artifact_id,
                name=safe_name[:255],
                kind=Artifact.Kind.IMPORT_SOURCE,
                classification=batch.classification,
                dataset_id=f"{batch.scope.code}-imports"[:128],
                quality_status="screened",
                created_by=batch.created_by,
            )
            version = ArtifactVersion.objects.create(
                id=version_id,
                artifact=artifact,
                version_number=1,
                original_filename=safe_name[:255],
                media_type=mime_type[:128] or "application/octet-stream",
                format=suffix[:16],
                size_bytes=len(content),
                sha256=digest,
                storage_key=storage_key,
                source_system=source_system[:128],
                classification=batch.classification,
                malware_status=ArtifactVersion.MalwareStatus.BASIC_SCREENED,
            )
            IngestionSourceFile.objects.create(
                batch=batch,
                artifact_version=version,
                file_name=safe_name[:255],
                sha256=digest,
                mime_type=mime_type[:128] or "application/octet-stream",
                size_bytes=len(content),
                screening={"malware": "basic_screened", "signature": "accepted"},
            )
            saved_key = default_storage.save(storage_key, ContentFile(content))
            stored = True
            if saved_key != storage_key:
                raise IngestionError(
                    "INGESTION_STORAGE_CONFLICT", "The deterministic source path already exists."
                )
    except Exception:
        if stored:
            default_storage.delete(storage_key)
        raise
    return version


def ensure_inline_source(batch: BulkImportBatch) -> ArtifactVersion:
    existing = batch.source_files.select_related("artifact_version").first()
    if existing:
        return existing.artifact_version
    content = json.dumps(batch.records, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return attach_source_bytes(
        batch,
        file_name=f"{batch.source_name or 'inline-records'}.json",
        content=content,
        mime_type="application/json",
        source_system="inline_records",
    )


def persist_validation(batch: BulkImportBatch) -> dict[str, object]:
    batch.status = BulkImportBatch.Status.VALIDATING
    batch.save(update_fields=["status", "updated_at"])
    normalized, result = validate_records(
        batch.domain, batch.records, batch.field_mapping, batch.scope
    )
    with transaction.atomic():
        batch.records = normalized
        batch.validation_result = result
        batch.status = (
            BulkImportBatch.Status.VALIDATED
            if result["valid"]
            else BulkImportBatch.Status.VALIDATION_FAILED
        )
        batch.save(update_fields=["records", "validation_result", "status", "updated_at"])
        batch.issues.all().delete()
        IngestionIssue.objects.bulk_create(
            [
                IngestionIssue(
                    batch=batch,
                    row_number=int(issue.get("row", 0)) or None,
                    field_name=str(issue.get("field", ""))[:128],
                    code=str(issue.get("code", "VALIDATION_ERROR"))[:128],
                    message=str(issue.get("message", "Validation failed."))[:512],
                    raw_value=issue.get("value"),
                )
                for issue in result.get("issues", [])
            ]
        )
    audit_identity_event(
        "ingestion.validated.v1",
        actor_id=batch.created_by,
        target_refs=[f"ingestion:{batch.id}", f"scope:{batch.scope.code}"],
        detail={"domain": batch.domain, "validation": result, "dry_run": True},
    )
    return result


def commit_batch(batch_id: str, *, actor_id: str) -> BulkImportBatch:
    batch = BulkImportBatch.objects.select_related("scope", "job").get(id=batch_id)
    if batch.status == BulkImportBatch.Status.COMMITTED:
        return batch
    if batch.status not in {BulkImportBatch.Status.QUEUED, BulkImportBatch.Status.COMMITTING}:
        raise IngestionError("IMPORT_NOT_COMMITTABLE", "Batch is not queued for commit.")
    if not batch.validation_result.get("valid"):
        raise IngestionError("IMPORT_VALIDATION_REQUIRED", "A passing dry run is required.")

    created = skipped = 0
    results: list[IngestionRecordResult] = []
    with transaction.atomic():
        locked = BulkImportBatch.objects.select_for_update().get(id=batch.id)
        if locked.status == BulkImportBatch.Status.COMMITTED:
            return locked
        locked.status = BulkImportBatch.Status.COMMITTING
        locked.save(update_fields=["status", "updated_at"])
        bulk_master_results: list[CommitResult] | None = None
        if locked.domain == "master_data" and len(locked.records) >= 500:
            current = {
                (item.kind.lower(), item.code.lower()): item
                for item in MasterDataItem.objects.filter(scope=locked.scope)
            }
            pending: list[MasterDataItem] = []
            for record in locked.records:
                identity = (str(record["kind"]).lower(), str(record["code"]).lower())
                if identity in current:
                    continue
                entity = MasterDataItem(
                    scope=locked.scope,
                    kind=str(record["kind"]),
                    code=str(record["code"]),
                    name_en=str(record["name_en"]),
                    name_zh_tw=str(record.get("name_zh_tw") or record["name_en"]),
                    source_system="ingestion",
                    source_refs=[f"ingestion:{locked.id}"],
                    classification=locked.classification,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
                current[identity] = entity
                pending.append(entity)
            MasterDataItem.objects.bulk_create(pending, batch_size=1_000)
            pending_ids = {item.id for item in pending}
            bulk_master_results = [
                CommitResult(
                    "master_data",
                    str(current[(str(record["kind"]).lower(), str(record["code"]).lower())].id),
                    current[(str(record["kind"]).lower(), str(record["code"]).lower())].id
                    in pending_ids,
                )
                for record in locked.records
            ]
        for row_number, record in enumerate(locked.records, start=1):
            commit = (
                bulk_master_results[row_number - 1]
                if bulk_master_results is not None
                else commit_record(locked, record, actor_id)
            )
            entity_type = commit.entity_type
            was_created = commit.created
            outcome = (
                IngestionRecordResult.Outcome.CREATED
                if was_created
                else IngestionRecordResult.Outcome.SKIPPED
            )
            created += int(was_created)
            skipped += int(not was_created)
            results.append(
                IngestionRecordResult(
                    batch=locked,
                    row_number=row_number,
                    outcome=outcome,
                    entity_type=entity_type,
                    entity_id=commit.entity_id,
                )
            )
        IngestionRecordResult.objects.bulk_create(results)
        balanced = created + skipped == len(locked.records)
        reconciliation = {
            "source_count": len(locked.records),
            "created_count": created,
            "updated_count": 0,
            "skipped_existing_count": skipped,
            "error_count": 0,
            "balanced": balanced,
            "scope": locked.scope.code,
        }
        report_hash = hashlib.sha256(
            json.dumps(reconciliation, sort_keys=True).encode("utf-8")
        ).hexdigest()
        ReconciliationReport.objects.update_or_create(
            batch=locked,
            defaults={
                "source_count": len(locked.records),
                "created_count": created,
                "updated_count": 0,
                "skipped_count": skipped,
                "failed_count": 0,
                "balanced": balanced,
                "report_hash": report_hash,
            },
        )
        locked.reconciliation = {**reconciliation, "report_hash": report_hash}
        locked.status = BulkImportBatch.Status.COMMITTED
        locked.committed_by = actor_id
        locked.committed_at = timezone.now()
        locked.save(
            update_fields=[
                "status",
                "reconciliation",
                "committed_by",
                "committed_at",
                "updated_at",
            ]
        )
    if batch.domain == "master_data":
        invalidate_master_data_cache()
    audit_identity_event(
        "ingestion.committed.v1",
        actor_id=actor_id,
        target_refs=[f"ingestion:{batch.id}", f"scope:{batch.scope.code}"],
        detail={"reconciliation": reconciliation},
    )
    return BulkImportBatch.objects.select_related("scope", "job").get(id=batch.id)
