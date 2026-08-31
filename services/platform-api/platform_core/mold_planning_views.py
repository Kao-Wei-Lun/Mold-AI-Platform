from __future__ import annotations

import uuid

from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Artifact, ArtifactVersion, MasterDataItem, MoldRevision, RuleProfile
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


def _comparison_profile_payload(profile: RuleProfile, baseline: RuleProfile) -> dict[str, object]:
    rules = list(profile.rules.filter(enabled=True).order_by("rule_id"))
    baseline_rules = {rule.rule_id: rule for rule in baseline.rules.filter(enabled=True)}
    current_rules = {rule.rule_id: rule for rule in rules}
    added = sorted(set(current_rules) - set(baseline_rules))
    removed = sorted(set(baseline_rules) - set(current_rules))
    modified = sorted(
        rule_id
        for rule_id in set(current_rules) & set(baseline_rules)
        if (
            current_rules[rule_id].operator,
            current_rules[rule_id].limit_value,
            current_rules[rule_id].unit,
            current_rules[rule_id].tolerance,
            current_rules[rule_id].severity,
        )
        != (
            baseline_rules[rule_id].operator,
            baseline_rules[rule_id].limit_value,
            baseline_rules[rule_id].unit,
            baseline_rules[rule_id].tolerance,
            baseline_rules[rule_id].severity,
        )
    )
    return {
        "profile_id": str(profile.id),
        "profile_key": profile.profile_key,
        "display_name": profile.profile_key.replace("-", " ").replace("_", " ").title(),
        "version": profile.version,
        "priority": profile.priority,
        "is_default": profile.is_default,
        "owner": profile.owner,
        "approved_by": profile.approved_by,
        "effective_from": profile.effective_from.isoformat() if profile.effective_from else None,
        "effective_to": profile.effective_to.isoformat() if profile.effective_to else None,
        "applicability": [
            {
                "dimension": item.dimension,
                "value_code": item.value_code,
                "match_mode": item.match_mode,
            }
            for item in profile.applicability_entries.all()
        ],
        "enabled_rule_count": len(rules),
        "risk_categories": sorted({rule.risk_type for rule in rules if rule.risk_type}),
        "high_risk_rules": [
            {
                "rule_id": rule.rule_id,
                "title": rule.title,
                "severity": rule.severity,
                "risk_type": rule.risk_type,
            }
            for rule in rules
            if rule.severity in {"high", "critical"}
        ],
        "difference_summary": {
            "baseline_profile_id": str(baseline.id),
            "added": added,
            "removed": removed,
            "modified": modified,
        },
    }


class MoldPlanningCandidateComparisonView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        profile_ids = request.data.get("profile_ids", [])
        if (
            not isinstance(profile_ids, list)
            or not 2 <= len(profile_ids) <= 3
            or len({str(item) for item in profile_ids}) != len(profile_ids)
        ):
            return _error(
                request,
                "VALIDATION_COMPARISON_SELECTION",
                "Select two or three distinct eligible candidates.",
                400,
            )
        preview = MoldPlanningResolutionPreviewView().post(request)
        if preview.status_code >= 400:
            return preview
        eligible_ids = {str(item["profile_id"]) for item in preview.data["candidates"]}
        requested_ids = [str(item) for item in profile_ids]
        if not set(requested_ids).issubset(eligible_ids):
            return _error(
                request,
                "RULE_PROFILE_COMPARISON_NOT_ELIGIBLE",
                "Comparison is limited to candidates eligible for this engineering context.",
                409,
            )
        profiles_by_id = {
            str(profile.id): profile
            for profile in RuleProfile.objects.prefetch_related(
                "applicability_entries", "rules"
            ).filter(id__in=requested_ids)
        }
        profiles = [profiles_by_id[item] for item in requested_ids]
        baseline = profiles[0]
        return Response(
            {
                "schema_version": "1.0",
                "context": preview.data["context"],
                "baseline_profile_id": str(baseline.id),
                "items": [
                    _comparison_profile_payload(profile, baseline) for profile in profiles
                ],
            }
        )
