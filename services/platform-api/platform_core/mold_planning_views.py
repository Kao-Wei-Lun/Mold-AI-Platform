from __future__ import annotations

import uuid

from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Artifact, ArtifactVersion, MasterDataItem, MoldRevision
from .rule_resolution import (
    RuleResolutionError,
    planning_context_for_revision,
    resolve_rule_profile_for_context,
)


def _error(request: Request, code: str, message: str, status: int, **detail) -> Response:
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": False,
                "request_id": getattr(request._request, "mold_ai_request_id", ""),
                **detail,
            }
        },
        status=status,
    )


class MoldPlanningResolutionPreviewView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        permissions = getattr(request._request, "mold_ai_permissions", set())
        if not {"registry:read", "rules:read"}.issubset(permissions):
            return _error(
                request,
                "ACCESS_DENIED",
                "Mold planning preview requires registry:read and rules:read.",
                403,
            )
        try:
            revision_id = uuid.UUID(str(request.data.get("mold_revision_id", "")))
        except ValueError:
            return _error(
                request,
                "VALIDATION_MOLD_REVISION",
                "mold_revision_id must be a UUID.",
                400,
            )
        scopes = set(getattr(request._request, "mold_ai_data_scopes", set())) or {"public-demo"}
        revision = (
            MoldRevision.objects.select_related("mold__project__scope", "mold__product_part")
            .filter(id=revision_id, mold__project__scope__code__in=scopes)
            .first()
        )
        if revision is None:
            return _error(
                request,
                "MOLD_REVISION_NOT_FOUND",
                "The mold revision is unavailable.",
                404,
            )

        artifact_version = None
        if request.data.get("cad_artifact_version_id"):
            try:
                artifact_version_id = uuid.UUID(str(request.data["cad_artifact_version_id"]))
            except ValueError:
                return _error(
                    request,
                    "VALIDATION_CAD_ARTIFACT_VERSION",
                    "cad_artifact_version_id must be a UUID.",
                    400,
                )
            artifact_version = (
                ArtifactVersion.objects.select_related("artifact")
                .filter(
                    id=artifact_version_id,
                    artifact__kind=Artifact.Kind.CAD_SOURCE,
                    artifact__mold_revision=revision,
                    classification=revision.mold.project.classification,
                )
                .first()
            )
            if artifact_version is None:
                return _error(
                    request,
                    "CAD_REVISION_MISMATCH",
                    "The CAD version does not belong to the selected mold revision.",
                    409,
                )

        raw_context = request.data.get("context", {})
        if not isinstance(raw_context, dict):
            return _error(
                request,
                "VALIDATION_RESOLUTION_CONTEXT",
                "context must be an object.",
                400,
            )
        try:
            context, sources = planning_context_for_revision(
                revision,
                artifact_version=artifact_version,
                extra_context=raw_context,
            )
        except RuleResolutionError as exc:
            return _error(request, exc.code, exc.user_message, 400, candidates=exc.candidates)

        kind_by_dimension = {
            "mold_type": MasterDataItem.Kind.MOLD_TYPE,
            "product_type": MasterDataItem.Kind.PRODUCT_TYPE,
            "material": MasterDataItem.Kind.MATERIAL,
            "molding_process": MasterDataItem.Kind.MOLDING_PROCESS,
            "location": MasterDataItem.Kind.LOCATION,
        }
        invalid_fields = [
            dimension
            for dimension, kind in kind_by_dimension.items()
            if context.get(dimension)
            and not MasterDataItem.objects.filter(
                scope=revision.mold.project.scope,
                kind=kind,
                code=context[dimension],
                status=MasterDataItem.Status.ACTIVE,
            ).exists()
        ]
        if invalid_fields:
            return _error(
                request,
                "VALIDATION_RESOLUTION_CONTEXT",
                "Planning context must use active governed engineering reference values.",
                400,
                invalid_fields=invalid_fields,
            )
        required = ("mold_type", "product_type", "material", "molding_process", "project")
        missing = [field for field in required if not context.get(field)]
        if missing:
            return _error(
                request,
                "PLANNING_CONTEXT_INCOMPLETE",
                "Complete the required engineering context before resolving a standard.",
                400,
                missing_fields=missing,
                context=context,
                sources=sources,
            )
        try:
            resolution = resolve_rule_profile_for_context(
                context,
                scope=revision.mold.project.scope,
                classification=revision.mold.project.classification,
            )
        except RuleResolutionError as exc:
            return _error(
                request,
                exc.code,
                exc.user_message,
                409 if exc.code == "RULE_PROFILE_AMBIGUOUS" else 422,
                candidates=exc.candidates,
                context=context,
                sources=sources,
            )
        return Response(
            {
                **resolution.snapshot,
                "mold_revision_id": str(revision.id),
                "cad_artifact_version_id": str(artifact_version.id) if artifact_version else None,
                "sources": sources,
                "missing_fields": [],
            }
        )
