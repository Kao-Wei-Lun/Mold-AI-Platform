from __future__ import annotations

import re

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .identity import audit_identity_event
from .models import Artifact, DataScope, Mold, MoldRevision, ProductPart, Project

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
        "revision_count": mold.revisions.count(),
        "created_at": mold.created_at.isoformat(),
        "updated_at": mold.updated_at.isoformat(),
    }
    if include_revisions:
        payload["revisions"] = [revision_payload(item) for item in mold.revisions.all()]
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
    }


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
        "references": references,
        "hard_delete_allowed": sum(references.values()) == 0,
    }


class ProjectListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        projects = Project.objects.select_related("scope").prefetch_related("parts", "molds")
        return Response({"schema_version": "1.0", "items": [project_payload(p) for p in projects]})

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
            code=str(request.data.get("scope", "public-demo")), is_active=True
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
        project = Project.objects.select_related("scope").filter(id=project_id).first()
        if project is None:
            return _error(request, "NOT_FOUND", "Project not found.", 404)
        return Response(project_payload(project))

    def patch(self, request: Request, project_id: str) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        project = Project.objects.select_related("scope").filter(id=project_id).first()
        if project is None:
            return _error(request, "NOT_FOUND", "Project not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if "code" in request.data and request.data["code"] != project.code:
            return _error(request, "CANONICAL_CODE_IMMUTABLE", "Project code is immutable.", 409)
        if int(request.data.get("row_version", 0)) != project.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "Project changed after loading.", 409)
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
        items = ProductPart.objects.select_related("project").prefetch_related("molds")
        if project_id := request.query_params.get("project_id"):
            items = items.filter(project_id=project_id)
        return Response({"schema_version": "1.0", "items": [part_payload(p) for p in items]})

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
        project = Project.objects.filter(id=request.data.get("project_id"), status="active").first()
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


class MoldListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        items = Mold.objects.select_related("project", "product_part").prefetch_related("revisions")
        if project_id := request.query_params.get("project_id"):
            items = items.filter(project_id=project_id)
        return Response({"schema_version": "1.0", "items": [mold_payload(m) for m in items]})

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
        project = Project.objects.filter(id=request.data.get("project_id"), status="active").first()
        if project is None:
            return _error(request, "VALIDATION_PROJECT", "An active project is required.", 400)
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
                mold_type=str(request.data.get("mold_type", "injection"))[:64],
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
            .filter(id=mold_id)
            .first()
        )
        if mold is None:
            return _error(request, "NOT_FOUND", "Mold not found.", 404)
        return Response(mold_payload(mold, include_revisions=True))

    def patch(self, request: Request, mold_id: str) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        mold = Mold.objects.select_related("project", "product_part").filter(id=mold_id).first()
        if mold is None:
            return _error(request, "NOT_FOUND", "Mold not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if "mold_code" in request.data and request.data["mold_code"] != mold.mold_code:
            return _error(request, "CANONICAL_CODE_IMMUTABLE", "Mold code is immutable.", 409)
        if int(request.data.get("row_version", 0)) != mold.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "Mold changed after loading.", 409)
        for field in ("name", "mold_type", "status"):
            if field in request.data:
                setattr(mold, field, str(request.data[field]).strip())
        if "cavity_count" in request.data:
            mold.cavity_count = int(request.data["cavity_count"])
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


class RevisionListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "registry:read"):
            return denied
        items = MoldRevision.objects.select_related("mold").prefetch_related("artifacts")
        if mold_id := request.query_params.get("mold_id"):
            items = items.filter(mold_id=mold_id)
        return Response({"schema_version": "1.0", "items": [revision_payload(r) for r in items]})

    def post(self, request: Request) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        revision_code, invalid = _valid_code(request, "revision_code")
        if invalid:
            return invalid
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        mold = Mold.objects.filter(id=request.data.get("mold_id"), status="active").first()
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
            .filter(id=revision_id)
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
        revision = MoldRevision.objects.select_related("mold").filter(id=revision_id).first()
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
            .filter(id=artifact_id, kind=Artifact.Kind.CAD_SOURCE)
            .first()
        )
        if artifact is None:
            return _error(request, "NOT_FOUND", "CAD artifact not found.", 404)
        return Response(artifact_governance_payload(artifact))

    def patch(self, request: Request, artifact_id: str) -> Response:
        if denied := _require(request, "registry:manage"):
            return denied
        artifact = (
            Artifact.objects.select_related("mold_revision__mold").filter(id=artifact_id).first()
        )
        if artifact is None:
            return _error(request, "NOT_FOUND", "CAD artifact not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        lifecycle = str(request.data.get("lifecycle_status", artifact.lifecycle_status))
        if lifecycle not in {"active", "quarantined", "archived"}:
            return _error(request, "VALIDATION_STATUS", "Invalid artifact lifecycle status.", 400)
        revision_id = request.data.get("mold_revision_id")
        if revision_id is not None:
            revision = MoldRevision.objects.filter(id=revision_id).first()
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
        artifact.save()
        audit_identity_event(
            "registry.artifact.updated.v1",
            actor_id=_actor(request),
            target_refs=[f"artifact:{artifact.id}"],
            detail={
                "reason": reason,
                "lifecycle_status": lifecycle,
                "mold_revision_id": str(artifact.mold_revision_id or ""),
            },
        )
        return Response(artifact_governance_payload(artifact))
