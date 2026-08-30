from __future__ import annotations

import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .identity import audit_identity_event
from .master_data import invalidate_master_data_cache
from .models import (
    Artifact,
    BulkArchiveOperation,
    BulkImportBatch,
    CAEStudy,
    DataScope,
    EnterpriseDataPolicy,
    MasterDataItem,
    Project,
    TrialCase,
)
from .pagination import PaginationValueError, paginate

MAX_BATCH_RECORDS = 1000
SUPPORTED_IMPORT_DOMAINS = {"master_data", "projects"}
SUPPORTED_ARCHIVE_DOMAINS = {"artifacts", "trials", "cae"}


def _error(request: Request, code: str, message: str, status: int, **details) -> Response:
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": status >= 500,
                "request_id": getattr(request._request, "mold_ai_request_id", ""),
                "details": details,
            }
        },
        status=status,
    )


def _require(request: Request, permission: str) -> Response | None:
    if permission in getattr(request._request, "mold_ai_permissions", set()):
        return None
    return _error(request, "ACCESS_DENIED", f"The account does not grant {permission}.", 403)


def _actor(request: Request) -> str:
    return str(getattr(request._request, "mold_ai_actor_id", "anonymous"))


def _scope(request: Request) -> tuple[DataScope | None, Response | None]:
    scope_code = (
        str(request.data.get("scope") if request.method not in {"GET", "HEAD"} else "").strip()
        or str(request.query_params.get("scope", "public-demo")).strip()
    )
    allowed = set(getattr(request._request, "mold_ai_data_scopes", set()))
    if scope_code not in allowed:
        return None, _error(
            request,
            "DATA_SCOPE_DENIED",
            "The requested data scope is not assigned to this account.",
            403,
            requested_scope=scope_code,
        )
    scope = DataScope.objects.filter(code=scope_code, is_active=True).first()
    if scope is None:
        return None, _error(request, "DATA_SCOPE_NOT_FOUND", "Data scope not found.", 404)
    return scope, None


def _policy(scope: DataScope) -> EnterpriseDataPolicy:
    policy, _ = EnterpriseDataPolicy.objects.get_or_create(
        scope=scope,
        defaults={
            "connector_mode": (
                EnterpriseDataPolicy.ConnectorMode.PUBLIC_DEMO
                if scope.classification == "public_demo"
                else EnterpriseDataPolicy.ConnectorMode.COMPANY
            ),
            "index_namespace": f"mold-ai-{scope.code}-index",
            "cache_namespace": f"mold-ai-{scope.code}-cache",
        },
    )
    return policy


def _policy_payload(policy: EnterpriseDataPolicy) -> dict[str, object]:
    cutoff = timezone.now() - timedelta(days=policy.retention_days)
    classification = policy.scope.classification
    eligible = {
        "artifacts": Artifact.objects.filter(
            classification=classification, created_at__lt=cutoff
        ).count(),
        "trials": TrialCase.objects.filter(
            classification=classification, created_at__lt=cutoff
        ).count(),
        "cae_studies": CAEStudy.objects.filter(
            classification=classification, created_at__lt=cutoff
        ).count(),
    }
    return {
        "policy_id": str(policy.id),
        "scope": policy.scope.code,
        "classification": classification,
        "connector_mode": policy.connector_mode,
        "retention_days": policy.retention_days,
        "retention_cutoff": cutoff.isoformat(),
        "retention_eligible": eligible,
        "purge_blocked": policy.legal_hold,
        "legal_hold": policy.legal_hold,
        "legal_hold_reason": policy.legal_hold_reason,
        "dlp_enabled": policy.dlp_enabled,
        "export_allowed": policy.export_allowed and not policy.legal_hold,
        "siem": {
            "enabled": policy.siem_enabled,
            "destination": policy.siem_destination or None,
            "status": "configured" if policy.siem_enabled else "disabled",
        },
        "isolation": {
            "index_namespace": policy.index_namespace,
            "cache_namespace": policy.cache_namespace,
            "cross_scope_queries": False,
            "cross_scope_exports": False,
        },
        "row_version": policy.row_version,
        "updated_by": policy.updated_by,
        "updated_at": policy.updated_at.isoformat(),
    }


def _mapped(record: object, mapping: dict[str, str]) -> dict[str, object]:
    if not isinstance(record, dict):
        return {}
    return {
        canonical: record.get(source)
        for canonical, source in mapping.items()
        if isinstance(canonical, str) and isinstance(source, str)
    } | {key: value for key, value in record.items() if key not in mapping.values()}


def _validate_records(
    domain: str,
    records: list[object],
    mapping: dict[str, str],
    scope: DataScope,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    normalized = [_mapped(record, mapping) for record in records]
    issues: list[dict[str, object]] = []
    seen: set[tuple[str, ...]] = set()
    valid_kinds = {item.value for item in MasterDataItem.Kind}
    for index, record in enumerate(normalized):
        required = ("kind", "code", "name_en") if domain == "master_data" else ("code", "name")
        missing = [field for field in required if not str(record.get(field, "")).strip()]
        if missing:
            issues.append({"row": index + 1, "code": "REQUIRED_FIELDS", "fields": missing})
            continue
        if domain == "master_data" and record["kind"] not in valid_kinds:
            issues.append({"row": index + 1, "code": "INVALID_KIND", "value": record["kind"]})
        key = (
            (str(record.get("kind", "")).lower(), str(record.get("code", "")).lower())
            if domain == "master_data"
            else (str(record.get("code", "")).lower(),)
        )
        if key in seen:
            issues.append({"row": index + 1, "code": "DUPLICATE_IN_BATCH", "key": key})
        seen.add(key)
    existing = 0
    for record in normalized:
        if domain == "master_data":
            existing += int(
                MasterDataItem.objects.filter(
                    scope=scope,
                    kind=record.get("kind", ""),
                    code__iexact=record.get("code", ""),
                ).exists()
            )
        else:
            existing += int(
                Project.objects.filter(scope=scope, code__iexact=record.get("code", "")).exists()
            )
    return normalized, {
        "valid": not issues,
        "record_count": len(records),
        "valid_count": len(records) - len({issue["row"] for issue in issues}),
        "existing_count": existing,
        "issues": issues,
    }


def _batch_payload(batch: BulkImportBatch, *, detail: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "batch_id": str(batch.id),
        "scope": batch.scope.code,
        "domain": batch.domain,
        "source_name": batch.source_name,
        "idempotency_key": batch.idempotency_key,
        "status": batch.status,
        "validation": batch.validation_result,
        "reconciliation": batch.reconciliation,
        "created_by": batch.created_by,
        "created_at": batch.created_at.isoformat(),
        "committed_by": batch.committed_by or None,
        "committed_at": batch.committed_at.isoformat() if batch.committed_at else None,
    }
    if detail:
        payload["field_mapping"] = batch.field_mapping
        payload["records"] = batch.records
    return payload


class EnterprisePolicyView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "enterprise:read"):
            return denied
        scope, invalid = _scope(request)
        if invalid:
            return invalid
        return Response(_policy_payload(_policy(scope)))

    def patch(self, request: Request) -> Response:
        if denied := _require(request, "enterprise:manage"):
            return denied
        scope, invalid = _scope(request)
        if invalid:
            return invalid
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            return _error(request, "VALIDATION_REASON_REQUIRED", "A reason is required.", 400)
        policy = _policy(scope)
        if int(request.data.get("row_version", 0)) != policy.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "Policy changed.", 409)
        connector_mode = str(request.data.get("connector_mode", policy.connector_mode))
        if connector_mode == "company" and scope.classification == "public_demo":
            return _error(
                request,
                "CONNECTOR_SCOPE_MISMATCH",
                "Company connectors require a non-public company data scope.",
                409,
            )
        index_namespace = str(request.data.get("index_namespace", policy.index_namespace)).strip()
        cache_namespace = str(request.data.get("cache_namespace", policy.cache_namespace)).strip()
        if not index_namespace or not cache_namespace or index_namespace == cache_namespace:
            return _error(
                request,
                "ISOLATION_NAMESPACE_INVALID",
                "Distinct index and cache namespaces are required.",
                400,
            )
        if (
            EnterpriseDataPolicy.objects.exclude(id=policy.id)
            .filter(index_namespace=index_namespace)
            .exists()
            or EnterpriseDataPolicy.objects.exclude(id=policy.id)
            .filter(cache_namespace=cache_namespace)
            .exists()
        ):
            return _error(
                request, "ISOLATION_NAMESPACE_CONFLICT", "Namespace is already assigned.", 409
            )
        retention_days = int(request.data.get("retention_days", policy.retention_days))
        if retention_days < 30 or retention_days > 36500:
            return _error(request, "VALIDATION_RETENTION", "Retention must be 30–36500 days.", 400)
        policy.connector_mode = connector_mode
        policy.retention_days = retention_days
        policy.legal_hold = bool(request.data.get("legal_hold", policy.legal_hold))
        policy.legal_hold_reason = str(
            request.data.get("legal_hold_reason", policy.legal_hold_reason)
        )[:512]
        if policy.legal_hold and not policy.legal_hold_reason:
            return _error(
                request, "VALIDATION_LEGAL_HOLD_REASON", "Legal hold reason is required.", 400
            )
        policy.dlp_enabled = bool(request.data.get("dlp_enabled", policy.dlp_enabled))
        policy.export_allowed = bool(request.data.get("export_allowed", policy.export_allowed))
        policy.siem_enabled = bool(request.data.get("siem_enabled", policy.siem_enabled))
        policy.siem_destination = str(
            request.data.get("siem_destination", policy.siem_destination)
        )[:255]
        if policy.siem_enabled and not policy.siem_destination:
            return _error(
                request, "VALIDATION_SIEM_DESTINATION", "SIEM destination is required.", 400
            )
        policy.index_namespace = index_namespace
        policy.cache_namespace = cache_namespace
        policy.row_version += 1
        policy.updated_by = _actor(request)
        policy.save()
        audit_identity_event(
            "enterprise.policy.updated.v1",
            actor_id=_actor(request),
            target_refs=[f"enterprise-policy:{policy.id}", f"scope:{scope.code}"],
            detail={"reason": reason, "connector_mode": connector_mode},
        )
        return Response(_policy_payload(policy))


class BulkImportListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "enterprise:read"):
            return denied
        scope, invalid = _scope(request)
        if invalid:
            return invalid
        batches = BulkImportBatch.objects.select_related("scope").filter(scope=scope)
        if status := request.query_params.get("status"):
            batches = batches.filter(status=status)
        try:
            records, page = paginate(
                request,
                batches,
                allowed_sort={"created_at": "created_at", "status": "status"},
                default_sort="-created_at",
            )
        except PaginationValueError as exc:
            return _error(request, "VALIDATION_PAGINATION", str(exc), 400)
        return Response(
            {
                "schema_version": "1.0",
                "items": [_batch_payload(batch) for batch in records],
                "page": page,
            }
        )

    def post(self, request: Request) -> Response:
        if denied := _require(request, "bulk:manage"):
            return denied
        scope, invalid = _scope(request)
        if invalid:
            return invalid
        domain = str(request.data.get("domain", ""))
        if domain not in SUPPORTED_IMPORT_DOMAINS:
            return _error(request, "IMPORT_DOMAIN_UNSUPPORTED", "Unsupported import domain.", 400)
        records = request.data.get("records", [])
        mapping = request.data.get("field_mapping", {})
        if not isinstance(records, list) or not 1 <= len(records) <= MAX_BATCH_RECORDS:
            return _error(
                request,
                "IMPORT_BATCH_SIZE",
                f"A batch must contain 1–{MAX_BATCH_RECORDS} records.",
                400,
            )
        if not isinstance(mapping, dict):
            return _error(
                request, "IMPORT_MAPPING_INVALID", "field_mapping must be an object.", 400
            )
        normalized, validation = _validate_records(domain, records, mapping, scope)
        idempotency_key = str(request.data.get("idempotency_key", "")).strip()
        if not idempotency_key:
            return _error(
                request, "VALIDATION_IDEMPOTENCY_KEY", "idempotency_key is required.", 400
            )
        existing = BulkImportBatch.objects.filter(idempotency_key=idempotency_key[:255]).first()
        if existing:
            if existing.scope_id != scope.id or existing.domain != domain:
                return _error(
                    request,
                    "IDEMPOTENCY_SCOPE_CONFLICT",
                    "The idempotency key belongs to another scope or domain.",
                    409,
                )
            return Response(_batch_payload(existing, detail=True), status=200)
        batch = BulkImportBatch.objects.create(
            scope=scope,
            domain=domain,
            source_name=str(request.data.get("source_name", "manual-json"))[:255],
            idempotency_key=idempotency_key[:255],
            records=normalized,
            field_mapping=mapping,
            validation_result=validation,
            status=(
                BulkImportBatch.Status.VALIDATED
                if validation["valid"]
                else BulkImportBatch.Status.FAILED
            ),
            created_by=_actor(request),
        )
        audit_identity_event(
            "bulk_import.validated.v1",
            actor_id=_actor(request),
            target_refs=[f"bulk-import:{batch.id}", f"scope:{scope.code}"],
            detail={"domain": domain, "validation": validation},
        )
        return Response(_batch_payload(batch, detail=True), status=201)


class BulkImportDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, batch_id: str) -> Response:
        if denied := _require(request, "enterprise:read"):
            return denied
        batch = BulkImportBatch.objects.select_related("scope").filter(id=batch_id).first()
        if batch is None or batch.scope.code not in getattr(
            request._request, "mold_ai_data_scopes", set()
        ):
            return _error(request, "NOT_FOUND", "Import batch not found.", 404)
        return Response(_batch_payload(batch, detail=True))

    def post(self, request: Request, batch_id: str) -> Response:
        if denied := _require(request, "bulk:manage"):
            return denied
        batch = BulkImportBatch.objects.select_related("scope").filter(id=batch_id).first()
        if batch is None or batch.scope.code not in getattr(
            request._request, "mold_ai_data_scopes", set()
        ):
            return _error(request, "NOT_FOUND", "Import batch not found.", 404)
        if request.data.get("action") != "commit":
            return _error(request, "VALIDATION_ACTION", "Use action=commit.", 400)
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            return _error(request, "VALIDATION_REASON_REQUIRED", "A reason is required.", 400)
        if batch.status != BulkImportBatch.Status.VALIDATED:
            return _error(request, "IMPORT_NOT_COMMITTABLE", "Batch is not validated.", 409)
        policy = _policy(batch.scope)
        created = skipped = 0
        with transaction.atomic():
            for record in batch.records:
                if batch.domain == "master_data":
                    existing = MasterDataItem.objects.filter(
                        scope=batch.scope,
                        kind=record["kind"],
                        code__iexact=str(record["code"]),
                    ).first()
                    was_created = existing is None
                    if was_created:
                        MasterDataItem.objects.create(
                            scope=batch.scope,
                            kind=record["kind"],
                            code=str(record["code"]),
                            name_en=str(record["name_en"]),
                            name_zh_tw=str(record.get("name_zh_tw") or record["name_en"]),
                            source_system="bulk_import",
                            source_refs=[f"bulk-import:{batch.id}"],
                            classification=batch.scope.classification,
                            created_by=_actor(request),
                            updated_by=_actor(request),
                        )
                else:
                    _, was_created = Project.objects.get_or_create(
                        scope=batch.scope,
                        code=str(record["code"]),
                        defaults={
                            "name": str(record["name"]),
                            "description": str(record.get("description", "")),
                            "classification": batch.scope.classification,
                            "created_by": _actor(request),
                            "updated_by": _actor(request),
                        },
                    )
                created += int(was_created)
                skipped += int(not was_created)
            batch.status = BulkImportBatch.Status.COMMITTED
            batch.reconciliation = {
                "source_count": len(batch.records),
                "created_count": created,
                "skipped_existing_count": skipped,
                "error_count": 0,
                "balanced": created + skipped == len(batch.records),
                "scope": batch.scope.code,
                "index_namespace": policy.index_namespace,
            }
            batch.committed_by = _actor(request)
            batch.committed_at = timezone.now()
            batch.save(update_fields=["status", "reconciliation", "committed_by", "committed_at"])
        if batch.domain == "master_data":
            invalidate_master_data_cache()
        audit_identity_event(
            "bulk_import.committed.v1",
            actor_id=_actor(request),
            target_refs=[f"bulk-import:{batch.id}", f"scope:{batch.scope.code}"],
            detail={"reason": reason, "reconciliation": batch.reconciliation},
        )
        return Response(_batch_payload(batch, detail=True))


def _scoped_records(domain: str, scope: DataScope, record_ids: list[str]) -> QuerySet | list:
    classification = scope.classification
    if domain == "artifacts":
        return Artifact.objects.filter(id__in=record_ids, classification=classification)
    if domain == "trials":
        return [
            item
            for item in TrialCase.objects.filter(id__in=record_ids, classification=classification)
            if scope.code in item.acl_scopes
        ]
    if domain == "cae":
        return [
            item
            for item in CAEStudy.objects.filter(id__in=record_ids, classification=classification)
            if scope.code in item.acl_scopes
        ]
    return []


class BulkArchiveView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        if denied := _require(request, "bulk:manage"):
            return denied
        scope, invalid = _scope(request)
        if invalid:
            return invalid
        domain = str(request.data.get("domain", ""))
        if domain not in SUPPORTED_ARCHIVE_DOMAINS:
            return _error(request, "ARCHIVE_DOMAIN_UNSUPPORTED", "Unsupported domain.", 400)
        raw_ids = request.data.get("record_ids", [])
        if not isinstance(raw_ids, list) or not 1 <= len(raw_ids) <= 100:
            return _error(request, "ARCHIVE_BATCH_SIZE", "Use 1–100 record IDs.", 400)
        try:
            record_ids = [str(uuid.UUID(str(item))) for item in raw_ids]
        except ValueError:
            return _error(request, "VALIDATION_RECORD_ID", "Record IDs must be UUIDs.", 400)
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            return _error(request, "VALIDATION_REASON_REQUIRED", "A reason is required.", 400)
        dry_run = bool(request.data.get("dry_run", True))
        policy = _policy(scope)
        records = list(_scoped_records(domain, scope, record_ids))
        result = {
            "requested_count": len(record_ids),
            "matched_count": len(records),
            "missing_or_denied_count": len(record_ids) - len(records),
            "legal_hold": policy.legal_hold,
            "would_archive_count": len(records) if not policy.legal_hold else 0,
        }
        status = "validated"
        if not dry_run and policy.legal_hold:
            status = "blocked_legal_hold"
        elif not dry_run:
            now = timezone.now()
            for item in records:
                if isinstance(item, Artifact):
                    item.lifecycle_status = "archived"
                    item.archive_reason = reason[:512]
                    item.archived_at = now
                    item.row_version += 1
                    item.save()
                elif isinstance(item, TrialCase):
                    item.lifecycle_status = TrialCase.LifecycleStatus.ARCHIVED
                    item.archive_reason = reason[:512]
                    item.row_version += 1
                    item.save()
                elif isinstance(item, CAEStudy):
                    item.lifecycle_status = CAEStudy.LifecycleStatus.ARCHIVED
                    item.archive_reason = reason[:512]
                    item.archived_at = now
                    item.row_version += 1
                    item.save()
            status = "committed"
            result["archived_count"] = len(records)
        operation = BulkArchiveOperation.objects.create(
            scope=scope,
            domain=domain,
            record_ids=record_ids,
            dry_run=dry_run,
            status=status,
            result=result,
            reason=reason[:512],
            actor_id=_actor(request),
        )
        audit_identity_event(
            "bulk_archive.evaluated.v1" if dry_run else "bulk_archive.executed.v1",
            actor_id=_actor(request),
            target_refs=[f"bulk-archive:{operation.id}", f"scope:{scope.code}"],
            detail={"reason": reason, "status": status, "result": result},
        )
        response_status = 409 if status == "blocked_legal_hold" else 201
        return Response(
            {
                "operation_id": str(operation.id),
                "scope": scope.code,
                "domain": domain,
                "dry_run": dry_run,
                "status": status,
                "result": result,
            },
            status=response_status,
        )
