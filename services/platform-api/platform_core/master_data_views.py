from __future__ import annotations

import re

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .identity import audit_identity_event
from .master_data import (
    MASTER_DATA_KINDS,
    active_options_payload,
    invalidate_master_data_cache,
    master_data_etag,
    master_data_payload,
)
from .models import DataScope, MasterDataItem

CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
SORT_FIELDS = {
    "code": "code",
    "-code": "-code",
    "name_en": "name_en",
    "-name_en": "-name_en",
    "name_zh_tw": "name_zh_tw",
    "-name_zh_tw": "-name_zh_tw",
    "updated_at": "updated_at",
    "-updated_at": "-updated_at",
    "sort_order": "sort_order",
    "-sort_order": "-sort_order",
}


def _error(request: Request, code: str, message: str, http_status: int, **detail) -> Response:
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": http_status >= 500,
                "request_id": getattr(request._request, "mold_ai_request_id", ""),
                **detail,
            }
        },
        status=http_status,
    )


def _has_permission(request: Request, permission: str) -> bool:
    return permission in getattr(request._request, "mold_ai_permissions", set())


def _require(request: Request, permission: str) -> Response | None:
    if _has_permission(request, permission):
        return None
    return _error(
        request,
        "ACCESS_DENIED",
        f"The account does not grant {permission} permission.",
        status.HTTP_403_FORBIDDEN,
    )


def _actor(request: Request) -> str:
    return str(getattr(request._request, "mold_ai_actor_id", "anonymous"))


def _item(item_id: str) -> MasterDataItem | None:
    return MasterDataItem.objects.select_related("scope").filter(id=item_id).first()


def _validate_payload(request: Request, *, create: bool) -> tuple[dict, Response | None]:
    fields: dict = {}
    if create:
        kind = str(request.data.get("kind", "")).strip()
        code = str(request.data.get("code", "")).strip()
        if kind not in MASTER_DATA_KINDS:
            return {}, _error(
                request, "VALIDATION_KIND", "A supported master-data kind is required.", 400
            )
        if not CODE_RE.fullmatch(code):
            return {}, _error(
                request,
                "VALIDATION_CODE",
                "code must use letters, numbers, dot, dash, slash or underscore.",
                400,
            )
        fields.update(kind=kind, code=code)
    for field in ("name_en", "name_zh_tw"):
        if create or field in request.data:
            value = str(request.data.get(field, "")).strip()
            if not value or len(value) > 255:
                return {}, _error(
                    request,
                    "VALIDATION_NAME",
                    f"{field} is required and must be at most 255 characters.",
                    400,
                )
            fields[field] = value
    for field in ("description_en", "description_zh_tw"):
        if field in request.data:
            fields[field] = str(request.data.get(field, "")).strip()
    if "sort_order" in request.data or create:
        try:
            fields["sort_order"] = int(request.data.get("sort_order", 100))
            if fields["sort_order"] < 0:
                raise ValueError
        except (TypeError, ValueError):
            return {}, _error(
                request, "VALIDATION_SORT_ORDER", "sort_order must be a non-negative integer.", 400
            )
    for field, empty in (("attributes", {}), ("aliases", []), ("source_refs", [])):
        if field in request.data:
            value = request.data.get(field)
            if not isinstance(value, type(empty)):
                return {}, _error(
                    request, "VALIDATION_STRUCTURE", f"{field} has an invalid structure.", 400
                )
            fields[field] = value
    for field in ("source_system", "classification"):
        if field in request.data:
            value = str(request.data.get(field, "")).strip()
            if not value:
                return {}, _error(
                    request, "VALIDATION_REQUIRED_FIELDS", f"{field} cannot be empty.", 400
                )
            fields[field] = value[: 64 if field == "source_system" else 32]
    if "status" in request.data:
        item_status = str(request.data.get("status", "")).strip()
        if item_status not in MasterDataItem.Status.values:
            return {}, _error(request, "VALIDATION_STATUS", "Unsupported master-data status.", 400)
        fields["status"] = item_status
    return fields, None


class MasterDataOptionsView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        denied = _require(request, "master-data:read")
        if denied:
            return denied
        return Response({"schema_version": "1.0", "results": active_options_payload()})


class MasterDataListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        denied = _require(request, "master-data:read")
        if denied:
            return denied
        queryset = MasterDataItem.objects.select_related("scope")
        kind = request.query_params.get("kind", "").strip()
        item_status = request.query_params.get("status", "").strip()
        search = request.query_params.get("search", "").strip()
        if kind:
            if kind not in MASTER_DATA_KINDS:
                return _error(request, "VALIDATION_KIND", "Unsupported master-data kind.", 400)
            queryset = queryset.filter(kind=kind)
        if item_status:
            if item_status not in MasterDataItem.Status.values:
                return _error(request, "VALIDATION_STATUS", "Unsupported master-data status.", 400)
            queryset = queryset.filter(status=item_status)
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name_en__icontains=search)
                | Q(name_zh_tw__icontains=search)
            )
        queryset = queryset.order_by(
            SORT_FIELDS.get(request.query_params.get("sort", "sort_order"), "sort_order"), "code"
        )
        try:
            page = max(1, int(request.query_params.get("page", "1")))
            page_size = min(100, max(1, int(request.query_params.get("page_size", "25"))))
        except ValueError:
            return _error(
                request, "VALIDATION_PAGINATION", "page and page_size must be integers.", 400
            )
        total = queryset.count()
        start = (page - 1) * page_size
        results = [
            master_data_payload(item, include_references=True)
            for item in queryset[start : start + page_size]
        ]
        return Response(
            {
                "results": results,
                "pagination": {"page": page, "page_size": page_size, "total": total},
            }
        )

    def post(self, request: Request) -> Response:
        denied = _require(request, "master-data:manage")
        if denied:
            return denied
        fields, invalid = _validate_payload(request, create=True)
        if invalid:
            return invalid
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            return _error(
                request,
                "VALIDATION_REASON_REQUIRED",
                "A creation reason is required.",
                400,
            )
        scope = DataScope.objects.filter(
            code=str(request.data.get("scope", "public-demo")), is_active=True
        ).first()
        if scope is None:
            return _error(request, "VALIDATION_SCOPE", "The selected data scope is invalid.", 400)
        actor = _actor(request)
        if MasterDataItem.objects.filter(
            scope=scope, kind=fields["kind"], code__iexact=fields["code"]
        ).exists():
            return _error(
                request,
                "MASTER_DATA_CODE_CONFLICT",
                "The canonical code already exists in this kind and scope.",
                409,
            )
        try:
            with transaction.atomic():
                item = MasterDataItem.objects.create(
                    scope=scope, created_by=actor, updated_by=actor, **fields
                )
                audit_identity_event(
                    "master_data.created.v1",
                    actor_id=actor,
                    target_refs=[f"master-data:{item.id}"],
                    detail={
                        "kind": item.kind,
                        "code": item.code,
                        "reason": reason,
                        "row_version": item.row_version,
                    },
                )
        except IntegrityError:
            return _error(
                request,
                "MASTER_DATA_CODE_CONFLICT",
                "The canonical code already exists in this kind and scope.",
                409,
            )
        invalidate_master_data_cache()
        response = Response(master_data_payload(item, include_references=True), status=201)
        response["ETag"] = master_data_etag(item)
        return response


class MasterDataDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, item_id: str) -> Response:
        denied = _require(request, "master-data:read")
        if denied:
            return denied
        item = _item(item_id)
        if item is None:
            return _error(request, "NOT_FOUND", "Master-data item not found.", 404)
        response = Response(master_data_payload(item, include_references=True))
        response["ETag"] = master_data_etag(item)
        return response

    def patch(self, request: Request, item_id: str) -> Response:
        denied = _require(request, "master-data:manage")
        if denied:
            return denied
        item = _item(item_id)
        if item is None:
            return _error(request, "NOT_FOUND", "Master-data item not found.", 404)
        if "code" in request.data and str(request.data.get("code")) != item.code:
            return _error(
                request,
                "CANONICAL_CODE_IMMUTABLE",
                "Canonical code cannot be changed; create a new item or add an alias.",
                409,
            )
        expected_etag = master_data_etag(item)
        if_match = request.headers.get("If-Match", "")
        try:
            row_version = int(request.data.get("row_version", 0))
        except (TypeError, ValueError):
            row_version = 0
        if if_match != expected_etag and row_version != item.row_version:
            return _error(
                request,
                "CONCURRENT_MODIFICATION",
                "The master-data item changed after it was loaded.",
                409,
                current=master_data_payload(item, include_references=True),
                etag=expected_etag,
            )
        fields, invalid = _validate_payload(request, create=False)
        if invalid:
            return invalid
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            return _error(
                request, "VALIDATION_REASON_REQUIRED", "A change reason is required.", 400
            )
        actor = _actor(request)
        previous_status = item.status
        with transaction.atomic():
            for field, value in fields.items():
                setattr(item, field, value)
            if item.status == MasterDataItem.Status.ARCHIVED and previous_status != item.status:
                item.archive_reason = reason
                item.archived_at = timezone.now()
            elif item.status != MasterDataItem.Status.ARCHIVED:
                item.archive_reason = ""
                item.archived_at = None
            item.updated_by = actor
            item.row_version += 1
            item.save()
            audit_identity_event(
                "master_data.updated.v1",
                actor_id=actor,
                target_refs=[f"master-data:{item.id}"],
                detail={
                    "kind": item.kind,
                    "code": item.code,
                    "reason": reason,
                    "row_version": item.row_version,
                    "status": item.status,
                },
            )
        invalidate_master_data_cache()
        response = Response(master_data_payload(item, include_references=True))
        response["ETag"] = master_data_etag(item)
        return response

    def delete(self, request: Request, item_id: str) -> Response:
        denied = _require(request, "master-data:manage")
        if denied:
            return denied
        item = _item(item_id)
        if item is None:
            return _error(request, "NOT_FOUND", "Master-data item not found.", 404)
        data = request.data if isinstance(request.data, dict) else {}
        mutable = data.copy()
        mutable["status"] = MasterDataItem.Status.ARCHIVED
        request._full_data = mutable
        return self.patch(request, item_id)
