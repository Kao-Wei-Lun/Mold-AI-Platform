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
from .models import (
    Artifact,
    AuditEvent,
    CAEStudy,
    DataScope,
    MasterDataItem,
    Mold,
    MoldPlan,
    MoldRevision,
    ProductPart,
    Project,
    ReviewRun,
    SimilaritySearch,
    TrialCase,
)
from .pagination import PaginationValueError, paginate

CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


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


def _require(request: Request, permission: str) -> Response | None:
    if permission in getattr(request._request, "mold_ai_permissions", set()):
        return None
    return _error(
        request,
        "ACCESS_DENIED",
        f"The account does not grant {permission} permission.",
        status.HTTP_403_FORBIDDEN,
    )


def _actor(request: Request) -> str:
    return str(getattr(request._request, "mold_ai_actor_id", "anonymous"))


def _allowed_scope_codes(request: Request) -> set[str]:
    return set(getattr(request._request, "mold_ai_data_scopes", set())) or {"public-demo"}


def _allowed_classifications(request: Request) -> list[str]:
    return list(
        DataScope.objects.filter(code__in=_allowed_scope_codes(request), is_active=True)
        .values_list("classification", flat=True)
        .distinct()
    )


def _required_text(
    request: Request, field: str, *, max_length: int = 255
) -> tuple[str, Response | None]:
    value = str(request.data.get(field, "")).strip()
    if not value or len(value) > max_length:
        return "", _error(
            request,
            "VALIDATION_REQUIRED_FIELDS",
            f"{field} is required and must be at most {max_length} characters.",
            400,
        )
    return value, None


def _valid_code(request: Request, field: str) -> tuple[str, Response | None]:
    value, invalid = _required_text(request, field, max_length=128)
    if invalid:
        return "", invalid
    if not CODE_RE.fullmatch(value):
        return "", _error(
            request,
            "VALIDATION_CODE",
            f"{field} must use letters, numbers, dot, dash, slash or underscore.",
            400,
        )
    return value, None


def _reason(request: Request) -> tuple[str, Response | None]:
    value = str(request.data.get("reason", "")).strip()
    if not value:
        return "", _error(
            request, "VALIDATION_REASON_REQUIRED", "A change reason is required.", 400
        )
    return value[:512], None


def _governed_mold_type(
    request: Request, project: Project, value: object
) -> tuple[str, Response | None]:
    code = str(value or "").strip()
    if (
        not code
        or not MasterDataItem.objects.filter(
            scope=project.scope,
            kind=MasterDataItem.Kind.MOLD_TYPE,
            code=code,
            status=MasterDataItem.Status.ACTIVE,
        ).exists()
    ):
        return "", _error(
            request,
            "VALIDATION_MOLD_TYPE",
            "mold_type must be an active governed engineering reference value.",
            400,
        )
    return code, None


def project_payload(project: Project) -> dict[str, object]:
    return {
        "id": str(project.id),
        "code": project.code,
        "name": project.name,
        "description": project.description,
        "scope": project.scope.code,
        "classification": project.classification,
        "status": project.status,
        "row_version": project.row_version,
        "part_count": project.parts.count(),
        "mold_count": project.molds.count(),
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def part_payload(part: ProductPart) -> dict[str, object]:
    return {
        "id": str(part.id),
        "project_id": str(part.project_id),
        "project_code": part.project.code,
        "part_number": part.part_number,
        "name": part.name,
        "product_type": part.product_type,
        "material_code": part.material_code,
        "status": part.status,
        "row_version": part.row_version,
        "mold_count": part.molds.count(),
        "created_at": part.created_at.isoformat(),
        "updated_at": part.updated_at.isoformat(),
    }


def mold_payload(mold: Mold, *, include_revisions: bool = False) -> dict[str, object]:
    revisions = list(mold.revisions.all())
    released = next(
        (item for item in revisions if item.status == MoldRevision.Status.RELEASED),
        None,
    )
    payload: dict[str, object] = {
        "id": str(mold.id),
        "project_id": str(mold.project_id),
        "project_code": mold.project.code,
        "product_part_id": str(mold.product_part_id) if mold.product_part_id else None,
        "part_number": mold.product_part.part_number if mold.product_part_id else None,
        "mold_code": mold.mold_code,
        "name": mold.name,
        "mold_type": mold.mold_type,
        "cavity_count": mold.cavity_count,
        "status": mold.status,
        "row_version": mold.row_version,
        "revision_count": len(revisions),
        "current_revision_id": str(released.id) if released else None,
        "current_revision_code": released.revision_code if released else None,
        "artifact_count": sum(len(list(item.artifacts.all())) for item in revisions),
        "created_at": mold.created_at.isoformat(),
        "updated_at": mold.updated_at.isoformat(),
        "allowed_actions": {
            Mold.Status.ACTIVE: ["edit", "create_revision", "retire", "archive"],
            Mold.Status.RETIRED: ["edit", "reactivate", "archive"],
            Mold.Status.ARCHIVED: [],
        }[mold.status],
    }
    if include_revisions:
        payload["revisions"] = [revision_payload(item) for item in revisions]
    return payload


def revision_payload(revision: MoldRevision) -> dict[str, object]:
    return {
        "id": str(revision.id),
        "mold_id": str(revision.mold_id),
        "mold_code": revision.mold.mold_code,
        "revision_code": revision.revision_code,
        "status": revision.status,
        "change_summary": revision.change_summary,
        "source_system": revision.source_system,
        "source_revision_id": revision.source_revision_id or None,
        "row_version": revision.row_version,
        "released_at": revision.released_at.isoformat() if revision.released_at else None,
        "artifact_count": revision.artifacts.count(),
        "created_at": revision.created_at.isoformat(),
        "updated_at": revision.updated_at.isoformat(),
        "allowed_actions": {
            MoldRevision.Status.DRAFT: ["edit", "release", "archive"],
            MoldRevision.Status.RELEASED: (
                ["archive"] if revision.mold.status != Mold.Status.ACTIVE else []
            ),
            MoldRevision.Status.SUPERSEDED: ["archive"],
            MoldRevision.Status.ARCHIVED: [],
        }[revision.status],
    }


def _mold_impact(mold: Mold) -> dict[str, int]:
    revisions = MoldRevision.objects.filter(mold=mold)
    artifact_filter = Q(cad_model__artifact_version__artifact__mold_revision__mold=mold)
    return {
        "draft_revisions": revisions.filter(status=MoldRevision.Status.DRAFT).count(),
        "released_revisions": revisions.filter(status=MoldRevision.Status.RELEASED).count(),
        "cad_artifacts": Artifact.objects.filter(mold_revision__mold=mold).count(),
        "mold_plans": MoldPlan.objects.filter(mold=mold).count(),
        "design_reviews": ReviewRun.objects.filter(artifact_filter).distinct().count(),
        "similarity_searches": SimilaritySearch.objects.filter(
            query_feature_set__cad_model__artifact_version__artifact__mold_revision__mold=mold
        ).count(),
        "cae_studies": CAEStudy.objects.filter(
            mold_revision_ref__startswith=f"{mold.mold_code}@"
        ).count(),
        "trial_cases": TrialCase.objects.filter(
            mold_revision_ref__startswith=f"{mold.mold_code}@"
        ).count(),
    }


def _suggest_revision_code(source: MoldRevision | None) -> str:
    if source is None:
        return "A"
    code = source.revision_code.strip()
    if len(code) == 1 and code.isalpha() and code.upper() != "Z":
        return chr(ord(code.upper()) + 1)
    if code.isdigit():
        return str(int(code) + 1).zfill(len(code))
    return f"{code}.1"


def _registry_subject(
    request: Request, *, mold_id: str | None = None, revision_id: str | None = None
) -> tuple[Mold | None, MoldRevision | None]:
    revisions = MoldRevision.objects.select_related(
        "mold__project__scope", "mold__product_part"
    ).filter(mold__project__scope__code__in=_allowed_scope_codes(request))
    revision = revisions.filter(id=revision_id).first() if revision_id else None
    molds = Mold.objects.select_related("project__scope", "product_part").filter(
        project__scope__code__in=_allowed_scope_codes(request)
    )
    mold = revision.mold if revision else molds.filter(id=mold_id).first()
    return mold, revision


def _visible_acl_record(request: Request, record: CAEStudy | TrialCase) -> bool:
    return bool(_allowed_scope_codes(request).intersection(set(record.acl_scopes or [])))


def _registry_engineering_records(
    request: Request, mold: Mold, revision: MoldRevision | None = None
) -> list[dict[str, object]]:
    revision_filter = Q(mold_revision=revision) if revision else Q(mold=mold)
    artifact_filter = (
        Q(cad_model__artifact_version__artifact__mold_revision=revision)
        if revision
        else Q(cad_model__artifact_version__artifact__mold_revision__mold=mold)
    )
    search_filter = (
        Q(query_feature_set__cad_model__artifact_version__artifact__mold_revision=revision)
        if revision
        else Q(query_feature_set__cad_model__artifact_version__artifact__mold_revision__mold=mold)
    )
    revision_refs = (
        [f"{mold.mold_code}@{revision.revision_code}"]
        if revision
        else [
            f"{mold.mold_code}@{code}"
            for code in mold.revisions.values_list("revision_code", flat=True)
        ]
    )
    records: list[dict[str, object]] = []

    for plan in MoldPlan.objects.filter(revision_filter).order_by("-updated_at"):
        records.append(
            {
                "record_type": "mold_plan",
                "record_id": str(plan.id),
                "title": f"{plan.plan_code} · {plan.name}",
                "status": plan.status,
                "owner": plan.owner_id,
                "revision_ref": f"{mold.mold_code}@{plan.mold_revision.revision_code}",
                "created_at": plan.created_at.isoformat(),
                "updated_at": plan.updated_at.isoformat(),
                "deep_link": (
                    "/engineering/mold-planning?deep_link_version=1.0"
                    f"&target=mold_plan&mold_plan_id={plan.id}"
                ),
            }
        )
    for review in (
        ReviewRun.objects.select_related(
            "profile", "cad_model__artifact_version__artifact__mold_revision"
        )
        .filter(artifact_filter)
        .distinct()
    ):
        linked_revision = review.cad_model.artifact_version.artifact.mold_revision
        records.append(
            {
                "record_type": "design_review",
                "record_id": str(review.id),
                "title": f"{review.profile.profile_key}@{review.profile.version}",
                "status": review.review_status,
                "owner": review.job.created_by,
                "revision_ref": f"{mold.mold_code}@{linked_revision.revision_code}",
                "created_at": review.created_at.isoformat(),
                "updated_at": (review.completed_at or review.created_at).isoformat(),
                "deep_link": (
                    "/engineering/design-review?deep_link_version=1.0"
                    f"&target=design_review&review_id={review.id}"
                ),
            }
        )
    for search in (
        SimilaritySearch.objects.select_related(
            "job", "query_feature_set__cad_model__artifact_version__artifact__mold_revision"
        )
        .filter(search_filter)
        .distinct()
    ):
        linked_revision = search.query_feature_set.cad_model.artifact_version.artifact.mold_revision
        records.append(
            {
                "record_type": "similarity_search",
                "record_id": str(search.id),
                "title": f"Similarity · top {search.top_k}",
                "status": search.job.state,
                "owner": search.job.created_by,
                "revision_ref": f"{mold.mold_code}@{linked_revision.revision_code}",
                "created_at": search.created_at.isoformat(),
                "updated_at": (search.completed_at or search.created_at).isoformat(),
                "deep_link": (
                    "/engineering/similarity?deep_link_version=1.0"
                    f"&target=similarity&search_id={search.id}"
                ),
            }
        )
    classifications = _allowed_classifications(request)
    for study in CAEStudy.objects.filter(
        mold_revision_ref__in=revision_refs, classification__in=classifications
    ):
        if not _visible_acl_record(request, study):
            continue
        records.append(
            {
                "record_type": "cae_study",
                "record_id": str(study.id),
                "title": study.study_code,
                "status": study.lifecycle_status,
                "owner": study.owner,
                "revision_ref": study.mold_revision_ref,
                "created_at": study.created_at.isoformat(),
                "updated_at": study.updated_at.isoformat(),
                "deep_link": f"/data/cae/{study.id}",
            }
        )
    for trial in TrialCase.objects.filter(
        mold_revision_ref__in=revision_refs, classification__in=classifications
    ):
        if not _visible_acl_record(request, trial):
            continue
        records.append(
            {
                "record_type": "trial_case",
                "record_id": str(trial.id),
                "title": trial.case_code,
                "status": trial.lifecycle_status,
                "owner": trial.operator_ref,
                "revision_ref": trial.mold_revision_ref,
                "created_at": trial.created_at.isoformat(),
                "updated_at": trial.updated_at.isoformat(),
                "deep_link": f"/data/trials/{trial.id}",
            }
        )
    return sorted(records, key=lambda item: str(item["updated_at"]), reverse=True)


def _registry_lineage(
    mold: Mold,
    revision: MoldRevision | None,
    records: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    revisions = [revision] if revision else list(mold.revisions.all())
    nodes: list[dict[str, object]] = [
        {
            "id": str(mold.project_id),
            "type": "project",
            "label": mold.project.code,
            "status": mold.project.status,
        },
        {"id": str(mold.id), "type": "mold", "label": mold.mold_code, "status": mold.status},
    ]
    edges: list[dict[str, object]] = [
        {"from": str(mold.project_id), "to": str(mold.id), "relationship": "contains"}
    ]
    if mold.product_part_id:
        nodes.append(
            {
                "id": str(mold.product_part_id),
                "type": "part",
                "label": mold.product_part.part_number,
                "status": mold.product_part.status,
            }
        )
        edges[0]["to"] = str(mold.product_part_id)
        edges.append(
            {"from": str(mold.product_part_id), "to": str(mold.id), "relationship": "contains"}
        )
    revision_ids: dict[str, str] = {}
    for item in revisions:
        if item is None:
            continue
        revision_ids[f"{mold.mold_code}@{item.revision_code}"] = str(item.id)
        nodes.append(
            {
                "id": str(item.id),
                "type": "mold_revision",
                "label": f"{mold.mold_code}@{item.revision_code}",
                "status": item.status,
            }
        )
        edges.append({"from": str(mold.id), "to": str(item.id), "relationship": "has_revision"})
        for artifact in item.artifacts.all():
            nodes.append(
                {
                    "id": str(artifact.id),
                    "type": "cad_artifact",
                    "label": artifact.name,
                    "status": artifact.lifecycle_status,
                }
            )
            edges.append(
                {"from": str(item.id), "to": str(artifact.id), "relationship": "has_artifact"}
            )
    for item in records:
        node_id = str(item["record_id"])
        nodes.append(
            {
                "id": node_id,
                "type": item["record_type"],
                "label": item["title"],
                "status": item["status"],
            }
        )
        parent_id = revision_ids.get(str(item["revision_ref"]), str(mold.id))
        edges.append({"from": parent_id, "to": node_id, "relationship": "used_by"})
    return {"nodes": nodes, "edges": edges}


class RegistryEngineeringHistoryView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(
        self,
        request: Request,
        mold_id: str | None = None,
        revision_id: str | None = None,
    ) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        mold, revision = _registry_subject(request, mold_id=mold_id, revision_id=revision_id)
        if mold is None or (revision_id and revision is None):
            return _error(request, "NOT_FOUND", "Registry record not found.", 404)
        records = _registry_engineering_records(request, mold, revision)
        refs = {f"mold:{mold.id}"}
        target_revisions = [revision] if revision else list(mold.revisions.all())
        for item in target_revisions:
            if item is None:
                continue
            refs.add(f"mold-revision:{item.id}")
            refs.update(
                f"artifact:{artifact_id}"
                for artifact_id in item.artifacts.values_list("id", flat=True)
            )
        refs.update(
            f"{item['record_type'].replace('_', '-')}:{item['record_id']}" for item in records
        )
        audit = [
            {
                "id": str(event.id),
                "event_type": event.event_type,
                "actor_id": event.actor_id,
                "target_refs": event.target_refs,
                "detail": event.detail,
                "payload_hash": event.payload_hash,
                "created_at": event.created_at.isoformat(),
            }
            for event in AuditEvent.objects.order_by("-created_at")
            if refs.intersection(set(event.target_refs or []))
        ]
        try:
            page_number = max(int(request.query_params.get("page", "1")), 1)
            page_size = min(max(int(request.query_params.get("page_size", "25")), 1), 100)
        except ValueError:
            return _error(
                request, "PAGINATION_INVALID", "page and page_size must be integers.", 400
            )
        offset = (page_number - 1) * page_size
        return Response(
            {
                "schema_version": "1.0",
                "subject": {
                    "mold_id": str(mold.id),
                    "mold_code": mold.mold_code,
                    "revision_id": str(revision.id) if revision else None,
                    "revision_code": revision.revision_code if revision else None,
                },
                "counts": {
                    kind: sum(1 for item in records if item["record_type"] == kind)
                    for kind in (
                        "mold_plan",
                        "design_review",
                        "similarity_search",
                        "cae_study",
                        "trial_case",
                    )
                },
                "items": records[offset : offset + page_size],
                "page": {
                    "number": page_number,
                    "size": page_size,
                    "total": len(records),
                    "has_next": offset + page_size < len(records),
                },
                "lineage": _registry_lineage(mold, revision, records),
                "audit_events": audit[:100],
            }
        )


def artifact_governance_payload(artifact: Artifact) -> dict[str, object]:
    versions = artifact.versions.all()
    references = {
        "versions": versions.count(),
        "jobs": sum(version.input_jobs.count() for version in versions),
        "feature_sets": sum(
            version.cad_model.feature_sets.count() if hasattr(version, "cad_model") else 0
            for version in versions
        ),
        "design_reviews": sum(
            version.cad_model.review_runs.count() if hasattr(version, "cad_model") else 0
            for version in versions
        ),
    }
    return {
        "artifact_id": str(artifact.id),
        "name": artifact.name,
        "mold_revision_id": str(artifact.mold_revision_id) if artifact.mold_revision_id else None,
        "mold_revision": (
            f"{artifact.mold_revision.mold.mold_code}@{artifact.mold_revision.revision_code}"
            if artifact.mold_revision_id
            else None
        ),
        "lifecycle_status": artifact.lifecycle_status,
        "quality_status": artifact.quality_status,
        "archive_reason": artifact.archive_reason or None,
        "archived_at": artifact.archived_at.isoformat() if artifact.archived_at else None,
        "row_version": artifact.row_version,
        "updated_at": artifact.updated_at.isoformat(),
        "references": references,
        "hard_delete_allowed": sum(references.values()) == 0,
    }


def _paginated_response(
    request: Request, queryset, serializer, *, allowed_sort: dict[str, str], default_sort: str
) -> Response:
    try:
        items, page = paginate(
            request, queryset, allowed_sort=allowed_sort, default_sort=default_sort
        )
    except PaginationValueError as exc:
        return _error(request, "VALIDATION_PAGINATION", str(exc), 400)
    return Response(
        {"schema_version": "1.0", "items": [serializer(item) for item in items], "page": page}
    )


class RegistryOverviewView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        scope_codes = _allowed_scope_codes(request)
        projects = Project.objects.filter(scope__code__in=scope_codes)
        molds = Mold.objects.filter(project__scope__code__in=scope_codes)
        revisions = MoldRevision.objects.filter(mold__project__scope__code__in=scope_codes)
        released = revisions.filter(status=MoldRevision.Status.RELEASED)
        return Response(
            {
                "schema_version": "1.0",
                "counts": {
                    "active_projects": projects.filter(status=Project.Status.ACTIVE).count(),
                    "active_molds": molds.filter(status=Mold.Status.ACTIVE).count(),
                    "released_revisions": released.count(),
                    "draft_revisions": revisions.filter(status=MoldRevision.Status.DRAFT).count(),
                    "released_without_cad": released.filter(artifacts__isnull=True).count(),
                    "pending_mapping": molds.filter(
                        status=Mold.Status.ACTIVE, product_part__isnull=True
                    ).count(),
                },
            }
        )


class ProjectListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        projects = (
            Project.objects.select_related("scope")
            .prefetch_related("parts", "molds")
            .filter(scope__code__in=_allowed_scope_codes(request))
        )
        if query := request.query_params.get("q"):
            projects = projects.filter(
                Q(code__icontains=query)
                | Q(name__icontains=query)
                | Q(parts__part_number__icontains=query)
                | Q(parts__name__icontains=query)
                | Q(molds__mold_code__icontains=query)
                | Q(molds__name__icontains=query)
                | Q(molds__revisions__revision_code__icontains=query)
                | Q(molds__revisions__source_revision_id__icontains=query)
            ).distinct()
        if status_filter := request.query_params.get("status"):
            projects = projects.filter(status=status_filter)
        return _paginated_response(
            request,
            projects,
            project_payload,
            allowed_sort={
                "code": "code",
                "name": "name",
                "status": "status",
                "created_at": "created_at",
                "updated_at": "updated_at",
            },
            default_sort="-updated_at",
        )

    def post(self, request: Request) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        code, invalid = _valid_code(request, "code")
        if invalid:
            return invalid
        name, invalid = _required_text(request, "name")
        if invalid:
            return invalid
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        scope = DataScope.objects.filter(
            code=str(request.data.get("scope", "public-demo")),
            code__in=_allowed_scope_codes(request),
            is_active=True,
        ).first()
        if scope is None:
            return _error(request, "VALIDATION_SCOPE", "The selected scope is invalid.", 400)
        actor = _actor(request)
        try:
            with transaction.atomic():
                project = Project.objects.create(
                    scope=scope,
                    code=code,
                    name=name,
                    description=str(request.data.get("description", "")).strip(),
                    created_by=actor,
                    updated_by=actor,
                )
                audit_identity_event(
                    "registry.project.created.v1",
                    actor_id=actor,
                    target_refs=[f"project:{project.id}"],
                    detail={"code": code, "reason": reason},
                )
        except IntegrityError:
            return _error(request, "PROJECT_CODE_CONFLICT", "Project code already exists.", 409)
        return Response(project_payload(project), status=201)


class ProjectDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, project_id: str) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        project = (
            Project.objects.select_related("scope")
            .filter(id=project_id, scope__code__in=_allowed_scope_codes(request))
            .first()
        )
        if project is None:
            return _error(request, "NOT_FOUND", "Project not found.", 404)
        return Response(project_payload(project))

    def patch(self, request: Request, project_id: str) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        project = (
            Project.objects.select_related("scope")
            .filter(id=project_id, scope__code__in=_allowed_scope_codes(request))
            .first()
        )
        if project is None:
            return _error(request, "NOT_FOUND", "Project not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if "code" in request.data and request.data["code"] != project.code:
            return _error(request, "CANONICAL_CODE_IMMUTABLE", "Project code is immutable.", 409)
        if int(request.data.get("row_version", 0)) != project.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "Project changed after loading.", 409)
        if "status" in request.data and request.data["status"] not in Project.Status.values:
            return _error(request, "VALIDATION_STATUS", "Project status is invalid.", 400)
        for field in ("name", "description", "status"):
            if field in request.data:
                setattr(project, field, str(request.data[field]).strip())
        project.row_version += 1
        project.updated_by = _actor(request)
        project.save()
        audit_identity_event(
            "registry.project.updated.v1",
            actor_id=_actor(request),
            target_refs=[f"project:{project.id}"],
            detail={"reason": reason, "status": project.status},
        )
        return Response(project_payload(project))


class PartListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        items = (
            ProductPart.objects.select_related("project")
            .prefetch_related("molds")
            .filter(project__scope__code__in=_allowed_scope_codes(request))
        )
        if project_id := request.query_params.get("project_id"):
            items = items.filter(project_id=project_id)
        if status_filter := request.query_params.get("status"):
            items = items.filter(status=status_filter)
        if product_type := request.query_params.get("product_type"):
            items = items.filter(product_type=product_type)
        if material_code := request.query_params.get("material_code"):
            items = items.filter(material_code=material_code)
        if query := request.query_params.get("q"):
            items = items.filter(
                Q(part_number__icontains=query)
                | Q(name__icontains=query)
                | Q(project__code__icontains=query)
                | Q(project__name__icontains=query)
                | Q(molds__mold_code__icontains=query)
                | Q(molds__name__icontains=query)
                | Q(molds__revisions__revision_code__icontains=query)
            ).distinct()
        return _paginated_response(
            request,
            items,
            part_payload,
            allowed_sort={
                "part_number": "part_number",
                "name": "name",
                "project_code": "project__code",
                "product_type": "product_type",
                "material_code": "material_code",
                "status": "status",
                "created_at": "created_at",
                "updated_at": "updated_at",
            },
            default_sort="-updated_at",
        )

    def post(self, request: Request) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        part_number, invalid = _valid_code(request, "part_number")
        if invalid:
            return invalid
        name, invalid = _required_text(request, "name")
        if invalid:
            return invalid
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        project = Project.objects.filter(
            id=request.data.get("project_id"),
            status="active",
            scope__code__in=_allowed_scope_codes(request),
        ).first()
        if project is None:
            return _error(request, "VALIDATION_PROJECT", "An active project is required.", 400)
        actor = _actor(request)
        if ProductPart.objects.filter(project=project, part_number=part_number).exists():
            return _error(request, "PART_NUMBER_CONFLICT", "Part number already exists.", 409)
        try:
            part = ProductPart.objects.create(
                project=project,
                part_number=part_number,
                name=name,
                product_type=str(request.data.get("product_type", "")).strip(),
                material_code=str(request.data.get("material_code", "")).strip(),
                created_by=actor,
                updated_by=actor,
            )
        except IntegrityError:
            return _error(request, "PART_NUMBER_CONFLICT", "Part number already exists.", 409)
        audit_identity_event(
            "registry.part.created.v1",
            actor_id=actor,
            target_refs=[f"part:{part.id}", f"project:{project.id}"],
            detail={"part_number": part_number, "reason": reason},
        )
        return Response(part_payload(part), status=201)


class PartDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, part_id: str) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        part = (
            ProductPart.objects.select_related("project")
            .prefetch_related("molds__revisions")
            .filter(id=part_id, project__scope__code__in=_allowed_scope_codes(request))
            .first()
        )
        if part is None:
            return _error(request, "NOT_FOUND", "Product part not found.", 404)
        payload = part_payload(part)
        payload["molds"] = [mold_payload(item, include_revisions=True) for item in part.molds.all()]
        return Response(payload)

    def patch(self, request: Request, part_id: str) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        part = (
            ProductPart.objects.select_related("project")
            .filter(id=part_id, project__scope__code__in=_allowed_scope_codes(request))
            .first()
        )
        if part is None:
            return _error(request, "NOT_FOUND", "Product part not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if "part_number" in request.data and request.data["part_number"] != part.part_number:
            return _error(request, "CANONICAL_CODE_IMMUTABLE", "Part number is immutable.", 409)
        if int(request.data.get("row_version", 0)) != part.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "Product part changed.", 409)
        if "status" in request.data and request.data["status"] not in ProductPart.Status.values:
            return _error(request, "VALIDATION_STATUS", "Product part status is invalid.", 400)
        for field in ("name", "product_type", "material_code", "status"):
            if field in request.data:
                setattr(part, field, str(request.data[field]).strip())
        part.row_version += 1
        part.updated_by = _actor(request)
        part.save()
        audit_identity_event(
            "registry.part.updated.v1",
            actor_id=_actor(request),
            target_refs=[f"part:{part.id}"],
            detail={"reason": reason, "status": part.status},
        )
        return Response(part_payload(part))


class MoldListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        items = (
            Mold.objects.select_related("project", "product_part")
            .prefetch_related("revisions__artifacts")
            .filter(project__scope__code__in=_allowed_scope_codes(request))
        )
        if project_id := request.query_params.get("project_id"):
            items = items.filter(project_id=project_id)
        if part_id := request.query_params.get("part_id"):
            if part_id == "unassigned":
                items = items.filter(product_part__isnull=True)
            else:
                items = items.filter(product_part_id=part_id)
        if status_filter := request.query_params.get("status"):
            items = items.filter(status=status_filter)
        if mold_type := request.query_params.get("mold_type"):
            items = items.filter(mold_type=mold_type)
        if product_type := request.query_params.get("product_type"):
            items = items.filter(product_part__product_type=product_type)
        if material_code := request.query_params.get("material_code"):
            items = items.filter(product_part__material_code=material_code)
        if revision_status := request.query_params.get("revision_status"):
            items = items.filter(revisions__status=revision_status)
        has_cad = request.query_params.get("has_cad")
        if has_cad == "true":
            items = items.filter(revisions__artifacts__isnull=False)
        elif has_cad == "false":
            items = items.exclude(revisions__artifacts__isnull=False)
        if query := request.query_params.get("q"):
            items = items.filter(
                Q(mold_code__icontains=query)
                | Q(name__icontains=query)
                | Q(project__code__icontains=query)
                | Q(project__name__icontains=query)
                | Q(product_part__part_number__icontains=query)
                | Q(product_part__name__icontains=query)
                | Q(revisions__revision_code__icontains=query)
                | Q(revisions__source_revision_id__icontains=query)
            )
        items = items.distinct()
        include_revisions = request.query_params.get("view") == "tree"
        return _paginated_response(
            request,
            items,
            lambda item: mold_payload(item, include_revisions=include_revisions),
            allowed_sort={
                "mold_code": "mold_code",
                "name": "name",
                "project_code": "project__code",
                "part_number": "product_part__part_number",
                "mold_type": "mold_type",
                "cavity_count": "cavity_count",
                "status": "status",
                "created_at": "created_at",
                "updated_at": "updated_at",
            },
            default_sort="-updated_at",
        )

    def post(self, request: Request) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        mold_code, invalid = _valid_code(request, "mold_code")
        if invalid:
            return invalid
        name, invalid = _required_text(request, "name")
        if invalid:
            return invalid
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        project = Project.objects.filter(
            id=request.data.get("project_id"),
            status="active",
            scope__code__in=_allowed_scope_codes(request),
        ).first()
        if project is None:
            return _error(request, "VALIDATION_PROJECT", "An active project is required.", 400)
        mold_type, invalid = _governed_mold_type(
            request, project, request.data.get("mold_type", "injection")
        )
        if invalid:
            return invalid
        part = None
        if request.data.get("product_part_id"):
            part = ProductPart.objects.filter(
                id=request.data["product_part_id"], project=project, status="active"
            ).first()
            if part is None:
                return _error(request, "VALIDATION_PART", "Part must belong to the project.", 400)
        try:
            cavity_count = int(request.data.get("cavity_count", 1))
            if not 1 <= cavity_count <= 128:
                raise ValueError
        except (TypeError, ValueError):
            return _error(request, "VALIDATION_CAVITY_COUNT", "cavity_count must be 1-128.", 400)
        actor = _actor(request)
        if Mold.objects.filter(project=project, mold_code=mold_code).exists():
            return _error(request, "MOLD_CODE_CONFLICT", "Mold code already exists.", 409)
        try:
            mold = Mold.objects.create(
                project=project,
                product_part=part,
                mold_code=mold_code,
                name=name,
                mold_type=mold_type,
                cavity_count=cavity_count,
                created_by=actor,
                updated_by=actor,
            )
        except IntegrityError:
            return _error(request, "MOLD_CODE_CONFLICT", "Mold code already exists.", 409)
        audit_identity_event(
            "registry.mold.created.v1",
            actor_id=actor,
            target_refs=[f"mold:{mold.id}", f"project:{project.id}"],
            detail={"mold_code": mold_code, "reason": reason},
        )
        return Response(mold_payload(mold), status=201)


class MoldDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, mold_id: str) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        mold = (
            Mold.objects.select_related("project", "product_part")
            .prefetch_related("revisions__artifacts")
            .filter(id=mold_id, project__scope__code__in=_allowed_scope_codes(request))
            .first()
        )
        if mold is None:
            return _error(request, "NOT_FOUND", "Mold not found.", 404)
        return Response(mold_payload(mold, include_revisions=True))

    def patch(self, request: Request, mold_id: str) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        mold = (
            Mold.objects.select_related("project", "product_part")
            .filter(id=mold_id, project__scope__code__in=_allowed_scope_codes(request))
            .first()
        )
        if mold is None:
            return _error(request, "NOT_FOUND", "Mold not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if "mold_code" in request.data and request.data["mold_code"] != mold.mold_code:
            return _error(request, "CANONICAL_CODE_IMMUTABLE", "Mold code is immutable.", 409)
        if int(request.data.get("row_version", 0)) != mold.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "Mold changed after loading.", 409)
        if "status" in request.data and request.data["status"] not in Mold.Status.values:
            return _error(request, "VALIDATION_STATUS", "Mold status is invalid.", 400)
        requested_status = str(request.data.get("status", mold.status))
        allowed_statuses = {
            Mold.Status.ACTIVE: {Mold.Status.ACTIVE, Mold.Status.RETIRED, Mold.Status.ARCHIVED},
            Mold.Status.RETIRED: {Mold.Status.RETIRED, Mold.Status.ACTIVE, Mold.Status.ARCHIVED},
            Mold.Status.ARCHIVED: {Mold.Status.ARCHIVED},
        }
        if requested_status not in allowed_statuses[mold.status]:
            return _error(
                request,
                "INVALID_LIFECYCLE_TRANSITION",
                "The requested mold lifecycle transition is invalid.",
                409,
            )
        if "mold_type" in request.data:
            mold_type, invalid = _governed_mold_type(
                request, mold.project, request.data["mold_type"]
            )
            if invalid:
                return invalid
            mold.mold_type = mold_type
        for field in ("name", "status"):
            if field in request.data:
                setattr(mold, field, str(request.data[field]).strip())
        if "cavity_count" in request.data:
            try:
                cavity_count = int(request.data["cavity_count"])
                if not 1 <= cavity_count <= 128:
                    raise ValueError
            except (TypeError, ValueError):
                return _error(
                    request, "VALIDATION_CAVITY_COUNT", "cavity_count must be 1-128.", 400
                )
            mold.cavity_count = cavity_count
        mold.row_version += 1
        mold.updated_by = _actor(request)
        mold.save()
        audit_identity_event(
            "registry.mold.updated.v1",
            actor_id=_actor(request),
            target_refs=[f"mold:{mold.id}"],
            detail={"reason": reason, "status": mold.status},
        )
        return Response(mold_payload(mold))


class MoldImpactPreviewView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, mold_id: str) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        mold = (
            Mold.objects.select_related("project")
            .filter(id=mold_id, project__scope__code__in=_allowed_scope_codes(request))
            .first()
        )
        if mold is None:
            return _error(request, "NOT_FOUND", "Mold not found.", 404)
        return Response(
            {
                "schema_version": "1.0",
                "mold_id": str(mold.id),
                "mold_code": mold.mold_code,
                "status": mold.status,
                "row_version": mold.row_version,
                "impact": _mold_impact(mold),
                "allowed_actions": mold_payload(mold)["allowed_actions"],
            }
        )


class MoldActionView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, mold_id: str) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        mold = (
            Mold.objects.select_related("project")
            .filter(id=mold_id, project__scope__code__in=_allowed_scope_codes(request))
            .first()
        )
        if mold is None:
            return _error(request, "NOT_FOUND", "Mold not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        try:
            row_version = int(request.data.get("row_version", 0))
        except (TypeError, ValueError):
            row_version = 0
        if row_version != mold.row_version:
            return _error(request, "VERSION_CONFLICT", "Mold changed after loading.", 409)
        action = str(request.data.get("action", "")).strip()
        transitions = {
            (Mold.Status.ACTIVE, "retire"): Mold.Status.RETIRED,
            (Mold.Status.ACTIVE, "archive"): Mold.Status.ARCHIVED,
            (Mold.Status.RETIRED, "reactivate"): Mold.Status.ACTIVE,
            (Mold.Status.RETIRED, "archive"): Mold.Status.ARCHIVED,
        }
        target = transitions.get((mold.status, action))
        if target is None:
            return _error(
                request,
                "INVALID_LIFECYCLE_TRANSITION",
                (
                    f"The {action or 'requested'} action is not allowed while "
                    f"the mold is {mold.status}."
                ),
                409,
                allowed_actions=mold_payload(mold)["allowed_actions"],
            )
        before = mold.status
        mold.status = target
        mold.row_version += 1
        mold.updated_by = _actor(request)
        mold.save(update_fields=["status", "row_version", "updated_by", "updated_at"])
        impact = _mold_impact(mold)
        audit_identity_event(
            f"registry.mold.{action}.v1",
            actor_id=_actor(request),
            target_refs=[f"mold:{mold.id}"],
            detail={"reason": reason, "before": before, "after": target, "impact": impact},
        )
        payload = mold_payload(mold, include_revisions=True)
        payload["impact"] = impact
        return Response(payload)


class MoldRevisionCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, mold_id: str) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        mold = (
            Mold.objects.select_related("project")
            .prefetch_related("revisions")
            .filter(
                id=mold_id,
                status=Mold.Status.ACTIVE,
                project__scope__code__in=_allowed_scope_codes(request),
            )
            .first()
        )
        if mold is None:
            return _error(request, "VALIDATION_MOLD", "An active mold is required.", 400)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        source = (
            next(
                (
                    item
                    for item in mold.revisions.all()
                    if item.status == MoldRevision.Status.RELEASED
                ),
                None,
            )
            or mold.revisions.order_by("-created_at").first()
        )
        requested_code = str(request.data.get("revision_code", "")).strip()
        revision_code = requested_code or _suggest_revision_code(source)
        if not CODE_RE.fullmatch(revision_code):
            return _error(request, "VALIDATION_CODE", "revision_code is invalid.", 400)
        if MoldRevision.objects.filter(mold=mold, revision_code=revision_code).exists():
            return _error(request, "REVISION_CODE_CONFLICT", "Revision already exists.", 409)
        actor = _actor(request)
        revision = MoldRevision.objects.create(
            mold=mold,
            revision_code=revision_code,
            status=MoldRevision.Status.DRAFT,
            change_summary=str(request.data.get("change_summary", "")).strip(),
            source_system="platform_demo",
            source_revision_id=str(source.id) if source else "",
            created_by=actor,
            updated_by=actor,
        )
        audit_identity_event(
            "registry.revision.created.v1",
            actor_id=actor,
            target_refs=[f"mold-revision:{revision.id}", f"mold:{mold.id}"],
            detail={
                "revision_code": revision_code,
                "reason": reason,
                "source_revision_id": str(source.id) if source else None,
            },
        )
        payload = revision_payload(revision)
        payload["suggested_revision_code"] = _suggest_revision_code(revision)
        return Response(payload, status=201)


class RevisionActionView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, revision_id: str) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        revision = (
            MoldRevision.objects.select_related("mold__project")
            .prefetch_related("artifacts")
            .filter(
                id=revision_id,
                mold__project__scope__code__in=_allowed_scope_codes(request),
            )
            .first()
        )
        if revision is None:
            return _error(request, "NOT_FOUND", "Mold revision not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        try:
            row_version = int(request.data.get("row_version", 0))
        except (TypeError, ValueError):
            row_version = 0
        if row_version != revision.row_version:
            return _error(request, "VERSION_CONFLICT", "Revision changed after loading.", 409)
        action = str(request.data.get("action", "")).strip()
        warnings: list[dict[str, str]] = []
        superseded_id: str | None = None
        with transaction.atomic():
            if action == "release" and revision.status == MoldRevision.Status.DRAFT:
                previous = (
                    MoldRevision.objects.filter(
                        mold=revision.mold, status=MoldRevision.Status.RELEASED
                    )
                    .exclude(id=revision.id)
                    .first()
                )
                if previous:
                    previous.status = MoldRevision.Status.SUPERSEDED
                    previous.row_version += 1
                    previous.updated_by = _actor(request)
                    previous.save(
                        update_fields=["status", "row_version", "updated_by", "updated_at"]
                    )
                    superseded_id = str(previous.id)
                if revision.artifacts.count() == 0:
                    warnings.append(
                        {
                            "code": "RELEASED_WITHOUT_CAD",
                            "message": "Demo release completed without a linked CAD artifact.",
                        }
                    )
                revision.status = MoldRevision.Status.RELEASED
                revision.released_at = timezone.now()
            elif action == "archive" and revision.status in {
                MoldRevision.Status.DRAFT,
                MoldRevision.Status.SUPERSEDED,
            }:
                revision.status = MoldRevision.Status.ARCHIVED
            elif (
                action == "archive"
                and revision.status == MoldRevision.Status.RELEASED
                and revision.mold.status != Mold.Status.ACTIVE
            ):
                revision.status = MoldRevision.Status.ARCHIVED
            else:
                return _error(
                    request,
                    "INVALID_LIFECYCLE_TRANSITION",
                    (
                        f"The {action or 'requested'} action is not allowed while "
                        f"the revision is {revision.status}."
                    ),
                    409,
                    allowed_actions=revision_payload(revision)["allowed_actions"],
                )
            revision.row_version += 1
            revision.updated_by = _actor(request)
            revision.save()
            audit_identity_event(
                f"registry.revision.{action}.v1",
                actor_id=_actor(request),
                target_refs=[f"mold-revision:{revision.id}", f"mold:{revision.mold_id}"],
                detail={
                    "reason": reason,
                    "status": revision.status,
                    "superseded_revision_id": superseded_id,
                    "warnings": warnings,
                },
            )
        payload = revision_payload(revision)
        payload.update({"warnings": warnings, "superseded_revision_id": superseded_id})
        return Response(payload)


class RevisionListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        items = (
            MoldRevision.objects.select_related("mold")
            .prefetch_related("artifacts")
            .filter(mold__project__scope__code__in=_allowed_scope_codes(request))
        )
        if mold_id := request.query_params.get("mold_id"):
            items = items.filter(mold_id=mold_id)
        if project_id := request.query_params.get("project_id"):
            items = items.filter(mold__project_id=project_id)
        if part_id := request.query_params.get("part_id"):
            items = items.filter(mold__product_part_id=part_id)
        if status_filter := request.query_params.get("status"):
            items = items.filter(status=status_filter)
        if query := request.query_params.get("q"):
            items = items.filter(
                Q(revision_code__icontains=query)
                | Q(source_revision_id__icontains=query)
                | Q(mold__mold_code__icontains=query)
                | Q(mold__name__icontains=query)
                | Q(mold__project__code__icontains=query)
                | Q(mold__product_part__part_number__icontains=query)
            )
        return _paginated_response(
            request,
            items,
            revision_payload,
            allowed_sort={
                "revision_code": "revision_code",
                "mold_code": "mold__mold_code",
                "created_at": "created_at",
                "updated_at": "updated_at",
                "status": "status",
            },
            default_sort="-updated_at",
        )

    def post(self, request: Request) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        revision_code, invalid = _valid_code(request, "revision_code")
        if invalid:
            return invalid
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        mold = Mold.objects.filter(
            id=request.data.get("mold_id"),
            status="active",
            project__scope__code__in=_allowed_scope_codes(request),
        ).first()
        if mold is None:
            return _error(request, "VALIDATION_MOLD", "An active mold is required.", 400)
        actor = _actor(request)
        if MoldRevision.objects.filter(mold=mold, revision_code=revision_code).exists():
            return _error(request, "REVISION_CODE_CONFLICT", "Revision already exists.", 409)
        try:
            revision = MoldRevision.objects.create(
                mold=mold,
                revision_code=revision_code,
                change_summary=str(request.data.get("change_summary", "")).strip(),
                created_by=actor,
                updated_by=actor,
            )
        except IntegrityError:
            return _error(request, "REVISION_CODE_CONFLICT", "Revision already exists.", 409)
        audit_identity_event(
            "registry.revision.created.v1",
            actor_id=actor,
            target_refs=[f"mold-revision:{revision.id}", f"mold:{mold.id}"],
            detail={"revision_code": revision_code, "reason": reason},
        )
        return Response(revision_payload(revision), status=201)


class RevisionDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, revision_id: str) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        revision = (
            MoldRevision.objects.select_related("mold")
            .prefetch_related("artifacts")
            .filter(
                id=revision_id,
                mold__project__scope__code__in=_allowed_scope_codes(request),
            )
            .first()
        )
        if revision is None:
            return _error(request, "NOT_FOUND", "Mold revision not found.", 404)
        payload = revision_payload(revision)
        payload["artifacts"] = [artifact_governance_payload(a) for a in revision.artifacts.all()]
        return Response(payload)

    def patch(self, request: Request, revision_id: str) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        revision = (
            MoldRevision.objects.select_related("mold")
            .filter(
                id=revision_id,
                mold__project__scope__code__in=_allowed_scope_codes(request),
            )
            .first()
        )
        if revision is None:
            return _error(request, "NOT_FOUND", "Mold revision not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if (
            "revision_code" in request.data
            and request.data["revision_code"] != revision.revision_code
        ):
            return _error(request, "CANONICAL_CODE_IMMUTABLE", "Revision code is immutable.", 409)
        if int(request.data.get("row_version", 0)) != revision.row_version:
            return _error(
                request, "CONCURRENT_MODIFICATION", "Revision changed after loading.", 409
            )
        new_status = str(request.data.get("status", revision.status))
        allowed = {
            MoldRevision.Status.DRAFT: {MoldRevision.Status.DRAFT, MoldRevision.Status.RELEASED},
            MoldRevision.Status.RELEASED: {
                MoldRevision.Status.RELEASED,
                MoldRevision.Status.SUPERSEDED,
                MoldRevision.Status.ARCHIVED,
            },
            MoldRevision.Status.SUPERSEDED: {
                MoldRevision.Status.SUPERSEDED,
                MoldRevision.Status.ARCHIVED,
            },
            MoldRevision.Status.ARCHIVED: {MoldRevision.Status.ARCHIVED},
        }
        if new_status not in allowed[revision.status]:
            return _error(
                request, "INVALID_STATE_TRANSITION", "Revision transition is invalid.", 409
            )
        if (
            new_status == MoldRevision.Status.ARCHIVED
            and revision.status == MoldRevision.Status.RELEASED
            and revision.mold.status == Mold.Status.ACTIVE
        ):
            return _error(
                request,
                "INVALID_LIFECYCLE_TRANSITION",
                "The current released revision cannot be archived while its mold is active.",
                409,
            )
        if (
            "change_summary" in request.data
            and revision.status != MoldRevision.Status.DRAFT
            and str(request.data["change_summary"]).strip() != revision.change_summary
        ):
            return _error(
                request,
                "RELEASED_REVISION_IMMUTABLE",
                "Released, superseded and archived revision content is immutable.",
                409,
            )
        with transaction.atomic():
            if new_status == MoldRevision.Status.RELEASED and revision.status != new_status:
                MoldRevision.objects.filter(
                    mold=revision.mold, status=MoldRevision.Status.RELEASED
                ).exclude(id=revision.id).update(status=MoldRevision.Status.SUPERSEDED)
                revision.released_at = timezone.now()
            if "change_summary" in request.data:
                revision.change_summary = str(request.data["change_summary"]).strip()
            revision.status = new_status
            revision.row_version += 1
            revision.updated_by = _actor(request)
            revision.save()
            audit_identity_event(
                "registry.revision.updated.v1",
                actor_id=_actor(request),
                target_refs=[f"mold-revision:{revision.id}"],
                detail={"reason": reason, "status": revision.status},
            )
        return Response(revision_payload(revision))


class ArtifactGovernanceView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, artifact_id: str) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        artifact = (
            Artifact.objects.select_related("mold_revision__mold")
            .prefetch_related(
                "versions__input_jobs",
                "versions__cad_model__feature_sets",
                "versions__cad_model__review_runs",
            )
            .filter(
                id=artifact_id,
                kind=Artifact.Kind.CAD_SOURCE,
                classification__in=_allowed_classifications(request),
            )
            .first()
        )
        if artifact is None:
            return _error(request, "NOT_FOUND", "CAD artifact not found.", 404)
        return Response(artifact_governance_payload(artifact))

    def patch(self, request: Request, artifact_id: str) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        artifact = (
            Artifact.objects.select_related("mold_revision__mold")
            .filter(id=artifact_id, classification__in=_allowed_classifications(request))
            .first()
        )
        if artifact is None:
            return _error(request, "NOT_FOUND", "CAD artifact not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if int(request.data.get("row_version", 0)) != artifact.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "CAD artifact changed.", 409)
        lifecycle = str(request.data.get("lifecycle_status", artifact.lifecycle_status))
        if lifecycle not in {"active", "quarantined", "archived"}:
            return _error(request, "VALIDATION_STATUS", "Invalid artifact lifecycle status.", 400)
        revision_id = request.data.get("mold_revision_id")
        if revision_id is not None:
            revision = MoldRevision.objects.filter(
                id=revision_id,
                mold__project__scope__code__in=_allowed_scope_codes(request),
            ).first()
            if revision is None:
                return _error(request, "VALIDATION_REVISION", "Mold revision not found.", 400)
            artifact.mold_revision = revision
        artifact.lifecycle_status = lifecycle
        if lifecycle == "archived":
            artifact.archived_at = timezone.now()
            artifact.archive_reason = reason
        elif lifecycle == "active":
            artifact.archived_at = None
            artifact.archive_reason = ""
        if "quality_status" in request.data:
            quality = str(request.data["quality_status"])
            if quality not in {"pending", "validated", "rejected"}:
                return _error(request, "VALIDATION_QUALITY", "Invalid quality status.", 400)
            artifact.quality_status = quality
        for field in ("name", "product_type", "material_code"):
            if field in request.data:
                value = str(request.data[field]).strip()
                if field == "name" and not value:
                    return _error(request, "VALIDATION_NAME", "Artifact name is required.", 400)
                setattr(artifact, field, value)
        artifact.row_version += 1
        artifact.save()
        audit_identity_event(
            "registry.artifact.updated.v1",
            actor_id=_actor(request),
            target_refs=[f"artifact:{artifact.id}"],
            detail={
                "reason": reason,
                "lifecycle_status": lifecycle,
                "mold_revision_id": str(artifact.mold_revision_id or ""),
                "row_version": artifact.row_version,
            },
        )
        return Response(artifact_governance_payload(artifact))
