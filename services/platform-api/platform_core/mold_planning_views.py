from __future__ import annotations

import hashlib
import json
import uuid

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .design_review import DesignReviewValidationError, create_design_review_records
from .identity import audit_identity_event
from .models import (
    Artifact,
    ArtifactVersion,
    MasterDataItem,
    MoldPlan,
    MoldPlanContext,
    MoldPlanHandoff,
    MoldPlanRequirement,
    MoldPlanResolution,
    MoldRevision,
    RuleProfile,
    RuleVersion,
)
from .pagination import PaginationValueError, paginate
from .rule_resolution import (
    RuleResolutionError,
    planning_context_for_revision,
    resolve_rule_profile_for_context,
)
from .tasks import run_design_review_job

CAD_EVALUATORS = {
    "bbox_dimension",
    "bbox_aspect_ratio",
    "cad_scalar",
    "edge_face_ratio",
    "quality_flag_absent",
    "unit_known",
    "surface_share",
}


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


def _actor(request: Request) -> str:
    return str(getattr(request._request, "mold_ai_actor_id", "anonymous"))


def _require(request: Request, permission: str) -> Response | None:
    if permission in getattr(request._request, "mold_ai_permissions", set()):
        return None
    return _error(request, "ACCESS_DENIED", f"The account does not grant {permission}.", 403)


def _scopes(request: Request) -> set[str]:
    return set(getattr(request._request, "mold_ai_data_scopes", set())) or {"public-demo"}


def _requirement_payload(requirement: MoldPlanRequirement) -> dict[str, object]:
    rule = requirement.rule_version
    return {
        "requirement_id": str(requirement.id),
        "rule_version_id": str(rule.id),
        "rule_id": rule.rule_id,
        "rule_version": rule.rule_version,
        "title": rule.title,
        "description": rule.description,
        "severity": rule.severity,
        "risk_type": rule.risk_type,
        "operator": rule.operator,
        "limit_value": rule.limit_value,
        "unit": rule.unit,
        "tolerance": rule.tolerance,
        "recommendation": rule.recommendation,
        "requirement_type": requirement.requirement_type,
        "evidence_requirement": requirement.evidence_requirement,
        "planning_status": requirement.planning_status,
        "source_reference": requirement.source_reference_snapshot,
    }


def _handoff_payload(handoff: MoldPlanHandoff) -> dict[str, object]:
    return {
        "handoff_id": str(handoff.id),
        "handoff_type": handoff.handoff_type,
        "target_ref": handoff.target_ref,
        "review_id": str(handoff.review_run_id) if handoff.review_run_id else None,
        "contract": handoff.contract_snapshot,
        "created_by": handoff.created_by,
        "created_at": handoff.created_at.isoformat(),
    }


def _requirement_contract(
    rule: RuleVersion, *, cad_available: bool
) -> tuple[str, dict[str, object], str]:
    if rule.evaluator in {"context_ratio", "context_value"}:
        evidence_kind = "manual_measurement"
        planning_status = MoldPlanRequirement.PlanningStatus.MANUAL_CONFIRMATION
        requirement_type = MoldPlanRequirement.RequirementType.MANUAL_CONFIRMATION
    elif rule.evaluator in CAD_EVALUATORS:
        evidence_kind = "cad_geometry"
        planning_status = (
            MoldPlanRequirement.PlanningStatus.READY_FOR_REVIEW
            if cad_available
            else MoldPlanRequirement.PlanningStatus.INSUFFICIENT_DATA
        )
        requirement_type = (
            MoldPlanRequirement.RequirementType.MUST
            if rule.severity in {"high", "critical"}
            else MoldPlanRequirement.RequirementType.SHOULD
        )
    else:
        evidence_kind = "cae_or_engineering_evidence"
        planning_status = MoldPlanRequirement.PlanningStatus.INSUFFICIENT_DATA
        requirement_type = (
            MoldPlanRequirement.RequirementType.MUST
            if rule.severity in {"high", "critical"}
            else MoldPlanRequirement.RequirementType.SHOULD
        )
    evidence = {
        "schema_version": "1.0",
        "kind": evidence_kind,
        "evaluator": rule.evaluator,
        "required": requirement_type != MoldPlanRequirement.RequirementType.SHOULD,
    }
    return requirement_type, evidence, planning_status


def _create_requirements(resolution: MoldPlanResolution) -> None:
    records = []
    for rule in resolution.selected_profile.rules.filter(enabled=True):
        requirement_type, evidence, planning_status = _requirement_contract(
            rule,
            cad_available=bool(resolution.plan.cad_artifact_version_id),
        )
        records.append(
            MoldPlanRequirement(
                resolution=resolution,
                rule_version=rule,
                requirement_type=requirement_type,
                evidence_requirement=evidence,
                planning_status=planning_status,
                source_reference_snapshot={
                    "schema_version": "1.0",
                    "rule_id": rule.rule_id,
                    "rule_version": rule.rule_version,
                    "reference": rule.reference,
                },
            )
        )
    MoldPlanRequirement.objects.bulk_create(records)


def _resolution_payload(resolution: MoldPlanResolution) -> dict[str, object]:
    requirements = [_requirement_payload(item) for item in resolution.requirements.all()]
    requirement_summary = {
        "total": len(requirements),
        "must": sum(item["requirement_type"] == "must" for item in requirements),
        "should": sum(item["requirement_type"] == "should" for item in requirements),
        "manual_confirmation": sum(
            item["requirement_type"] == "manual_confirmation" for item in requirements
        ),
        "high_risk": sum(item["severity"] in {"high", "critical"} for item in requirements),
        "cad_evidence": sum(
            item["evidence_requirement"]["kind"] == "cad_geometry" for item in requirements
        ),
        "cae_evidence": sum(
            item["evidence_requirement"]["kind"] == "cae_or_engineering_evidence"
            for item in requirements
        ),
        "insufficient_data": sum(
            item["planning_status"] == "insufficient_data" for item in requirements
        ),
    }
    return {
        "resolution_id": str(resolution.id),
        "resolution_number": resolution.resolution_number,
        "context_checksum": resolution.context_checksum,
        "selected_profile_id": str(resolution.selected_profile_id),
        "selected_profile_key": resolution.selected_profile.profile_key,
        "selected_profile_version": resolution.selected_profile.version,
        "ruleset_checksum": resolution.ruleset_checksum,
        "applicability_checksum": resolution.applicability_checksum,
        "selection_mode": resolution.selection_mode,
        "reason": resolution.reason,
        "override_reason": resolution.override_reason or None,
        "context": resolution.context_snapshot,
        "candidates": resolution.candidate_snapshot,
        "excluded_summary": resolution.exclusion_summary,
        "resolved_by": resolution.resolved_by,
        "resolved_at": resolution.resolved_at.isoformat(),
        "requirement_summary": requirement_summary,
        "requirements": requirements,
        "handoffs": [_handoff_payload(item) for item in resolution.handoffs.all()],
    }


def mold_plan_payload(plan: MoldPlan, *, detail: bool = False) -> dict[str, object]:
    latest = next(iter(plan.resolutions.all()), None)
    payload: dict[str, object] = {
        "plan_id": str(plan.id),
        "plan_code": plan.plan_code,
        "name": plan.name,
        "purpose": plan.purpose,
        "project_id": str(plan.project_id),
        "project_code": plan.project.code,
        "part_id": str(plan.part_id) if plan.part_id else None,
        "part_number": plan.part.part_number if plan.part_id else None,
        "mold_id": str(plan.mold_id),
        "mold_code": plan.mold.mold_code,
        "mold_revision_id": str(plan.mold_revision_id),
        "mold_revision": plan.mold_revision.revision_code,
        "cad_artifact_version_id": (
            str(plan.cad_artifact_version_id) if plan.cad_artifact_version_id else None
        ),
        "status": plan.status,
        "owner_id": plan.owner_id,
        "scope": plan.scope.code,
        "classification": plan.classification,
        "row_version": plan.row_version,
        "latest_resolution": _resolution_payload(latest) if latest else None,
        "created_at": plan.created_at.isoformat(),
        "updated_at": plan.updated_at.isoformat(),
        "archived_at": plan.archived_at.isoformat() if plan.archived_at else None,
        "archive_reason": plan.archive_reason or None,
    }
    if detail:
        payload["context"] = {
            item.dimension: {
                "value_code": item.value_code,
                "source_type": item.source_type,
                "source_ref": item.source_ref,
                "confirmed_by": item.confirmed_by or None,
                "confirmed_at": item.confirmed_at.isoformat() if item.confirmed_at else None,
            }
            for item in plan.context_entries.all()
        }
        payload["resolutions"] = [_resolution_payload(item) for item in plan.resolutions.all()]
    return payload


def mold_plan_queryset(request: Request):
    return (
        MoldPlan.objects.select_related(
            "project", "part", "mold", "mold_revision", "cad_artifact_version", "scope"
        )
        .prefetch_related(
            "context_entries",
            "resolutions__selected_profile",
            "resolutions__requirements__rule_version",
            "resolutions__handoffs__review_run",
        )
        .filter(scope__code__in=_scopes(request))
    )


def _context_checksum(context: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(context, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


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
                "items": [_comparison_profile_payload(profile, baseline) for profile in profiles],
            }
        )


class MoldPlanListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "mold-planning:read"):
            return denied
        plans = mold_plan_queryset(request)
        if query := request.query_params.get("q"):
            plans = plans.filter(
                Q(plan_code__icontains=query)
                | Q(name__icontains=query)
                | Q(mold__mold_code__icontains=query)
            )
        if status_filter := request.query_params.get("status"):
            plans = plans.filter(status=status_filter)
        if owner := request.query_params.get("owner"):
            plans = plans.filter(owner_id=owner)
        try:
            records, page = paginate(
                request,
                plans,
                allowed_sort={
                    "updated_at": "updated_at",
                    "created_at": "created_at",
                    "name": "name",
                    "plan_code": "plan_code",
                },
                default_sort="-updated_at",
            )
        except PaginationValueError as exc:
            return _error(request, "VALIDATION_PAGINATION", str(exc), 400)
        return Response(
            {
                "schema_version": "1.0",
                "items": [mold_plan_payload(plan) for plan in records],
                "page": page,
            }
        )

    def post(self, request: Request) -> Response:
        if denied := _require(request, "mold-planning:create"):
            return denied
        name = str(request.data.get("name", "")).strip()
        purpose = str(request.data.get("purpose", "")).strip()
        if not 3 <= len(name) <= 120:
            return _error(
                request,
                "VALIDATION_PLAN_NAME",
                "name must contain between 3 and 120 characters.",
                400,
            )
        if purpose not in MoldPlan.Purpose.values:
            return _error(request, "VALIDATION_PLAN_PURPOSE", "purpose is invalid.", 400)
        preview = MoldPlanningResolutionPreviewView().post(request)
        if preview.status_code >= 400:
            return preview
        revision = MoldRevision.objects.select_related(
            "mold__project__scope", "mold__product_part"
        ).get(id=preview.data["mold_revision_id"])
        artifact_version = None
        if preview.data["cad_artifact_version_id"]:
            artifact_version = ArtifactVersion.objects.get(
                id=preview.data["cad_artifact_version_id"]
            )
        actor = _actor(request)
        with transaction.atomic():
            plan = MoldPlan.objects.create(
                plan_code=f"MP-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
                name=name,
                purpose=purpose,
                project=revision.mold.project,
                part=revision.mold.product_part,
                mold=revision.mold,
                mold_revision=revision,
                cad_artifact_version=artifact_version,
                owner_id=str(request.data.get("owner_id") or actor)[:128],
                scope=revision.mold.project.scope,
                classification=revision.mold.project.classification,
                created_by=actor,
                updated_by=actor,
            )
            MoldPlanContext.objects.bulk_create(
                [
                    MoldPlanContext(
                        plan=plan,
                        dimension=dimension,
                        value_code=value,
                        source_type=preview.data["sources"][dimension]["source_type"],
                        source_ref=preview.data["sources"][dimension]["source_ref"],
                        confirmed_by=(
                            actor
                            if preview.data["sources"][dimension]["source_type"] == "user_confirmed"
                            else ""
                        ),
                        confirmed_at=(
                            timezone.now()
                            if preview.data["sources"][dimension]["source_type"] == "user_confirmed"
                            else None
                        ),
                    )
                    for dimension, value in preview.data["context"].items()
                ]
            )
            audit_identity_event(
                "mold_plan.create.v1",
                actor_id=actor,
                target_refs=[str(plan.id), str(revision.id)],
                detail={"plan_code": plan.plan_code, "purpose": purpose},
            )
        plan = mold_plan_queryset(request).get(id=plan.id)
        return Response(mold_plan_payload(plan, detail=True), status=201)


class MoldPlanDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, plan_id: uuid.UUID) -> Response:
        if denied := _require(request, "mold-planning:read"):
            return denied
        plan = mold_plan_queryset(request).filter(id=plan_id).first()
        if plan is None:
            return _error(request, "MOLD_PLAN_NOT_FOUND", "The mold plan is unavailable.", 404)
        return Response(mold_plan_payload(plan, detail=True))

    def patch(self, request: Request, plan_id: uuid.UUID) -> Response:
        if denied := _require(request, "mold-planning:create"):
            return denied
        with transaction.atomic():
            plan = (
                mold_plan_queryset(request)
                .select_for_update(of=("self",))
                .filter(id=plan_id)
                .first()
            )
            if plan is None:
                return _error(request, "MOLD_PLAN_NOT_FOUND", "The mold plan is unavailable.", 404)
            if plan.status != MoldPlan.Status.DRAFT:
                return _error(
                    request,
                    "MOLD_PLAN_IMMUTABLE",
                    "Only draft mold plans can be edited.",
                    409,
                )
            if int(request.data.get("row_version", 0)) != plan.row_version:
                return _error(
                    request,
                    "CONCURRENCY_CONFLICT",
                    "The mold plan changed after it was loaded.",
                    409,
                    current=mold_plan_payload(plan),
                )
            name = str(request.data.get("name", plan.name)).strip()
            purpose = str(request.data.get("purpose", plan.purpose)).strip()
            if not 3 <= len(name) <= 120 or purpose not in MoldPlan.Purpose.values:
                return _error(
                    request,
                    "VALIDATION_MOLD_PLAN",
                    "The plan name or purpose is invalid.",
                    400,
                )
            plan.name = name
            plan.purpose = purpose
            plan.owner_id = str(request.data.get("owner_id", plan.owner_id))[:128]
            plan.updated_by = _actor(request)
            plan.row_version += 1
            plan.save(
                update_fields=[
                    "name",
                    "purpose",
                    "owner_id",
                    "updated_by",
                    "row_version",
                    "updated_at",
                ]
            )
            audit_identity_event(
                "mold_plan.update.v1",
                actor_id=_actor(request),
                target_refs=[str(plan.id)],
                detail={"row_version": plan.row_version},
            )
        return Response(mold_plan_payload(mold_plan_queryset(request).get(id=plan.id), detail=True))


class MoldPlanResolveView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, plan_id: uuid.UUID) -> Response:
        if denied := _require(request, "mold-planning:create"):
            return denied
        with transaction.atomic():
            plan = (
                mold_plan_queryset(request)
                .select_for_update(of=("self",))
                .filter(id=plan_id)
                .first()
            )
            if plan is None:
                return _error(request, "MOLD_PLAN_NOT_FOUND", "The mold plan is unavailable.", 404)
            if plan.status in {MoldPlan.Status.COMPLETED, MoldPlan.Status.ARCHIVED}:
                return _error(
                    request,
                    "MOLD_PLAN_IMMUTABLE",
                    "Completed or archived plans cannot be resolved again.",
                    409,
                )
            context = {item.dimension: item.value_code for item in plan.context_entries.all()}
            try:
                resolution = resolve_rule_profile_for_context(
                    context,
                    scope=plan.scope,
                    classification=plan.classification,
                )
            except RuleResolutionError as exc:
                return _error(
                    request,
                    exc.code,
                    exc.user_message,
                    409 if exc.code == "RULE_PROFILE_AMBIGUOUS" else 422,
                    candidates=exc.candidates,
                )
            snapshot = resolution.snapshot
            record = MoldPlanResolution.objects.create(
                plan=plan,
                resolution_number=plan.resolutions.count() + 1,
                context_checksum=_context_checksum(context),
                selected_profile=resolution.profile,
                ruleset_checksum=resolution.profile.ruleset_checksum,
                applicability_checksum=snapshot["applicability_checksum"],
                selection_mode=snapshot["selection_mode"],
                reason=snapshot["reason"],
                override_reason=snapshot.get("override_reason") or "",
                context_snapshot=context,
                candidate_snapshot=snapshot["candidates"],
                exclusion_summary=snapshot.get("excluded_summary", []),
                resolved_by=_actor(request),
            )
            _create_requirements(record)
            plan.status = MoldPlan.Status.READY
            plan.updated_by = _actor(request)
            plan.row_version += 1
            plan.save(update_fields=["status", "updated_by", "row_version", "updated_at"])
            audit_identity_event(
                "mold_plan.resolve.v1",
                actor_id=_actor(request),
                target_refs=[str(plan.id), str(record.id), str(resolution.profile.id)],
                detail={
                    "resolution_number": record.resolution_number,
                    "context_checksum": record.context_checksum,
                    "selection_mode": record.selection_mode,
                },
            )
        return Response(mold_plan_payload(mold_plan_queryset(request).get(id=plan.id), detail=True))


class MoldPlanHandoffView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, plan_id: uuid.UUID, handoff_type: str) -> Response:
        if denied := _require(request, "mold-planning:create"):
            return denied
        if handoff_type not in MoldPlanHandoff.HandoffType.values:
            return _error(
                request,
                "VALIDATION_HANDOFF_TYPE",
                "The requested engineering handoff is not supported.",
                400,
            )
        plan = mold_plan_queryset(request).filter(id=plan_id).first()
        if plan is None:
            return _error(request, "MOLD_PLAN_NOT_FOUND", "The mold plan is unavailable.", 404)
        if int(request.data.get("row_version", 0)) != plan.row_version:
            return _error(
                request,
                "CONCURRENCY_CONFLICT",
                "The mold plan changed after it was loaded.",
                409,
            )
        if plan.status not in {MoldPlan.Status.READY, MoldPlan.Status.COMPLETED}:
            return _error(
                request,
                "MOLD_PLAN_NOT_READY",
                "Resolve the mold plan before starting an engineering handoff.",
                409,
            )
        resolution = next(iter(plan.resolutions.all()), None)
        if resolution is None:
            return _error(
                request,
                "MOLD_PLAN_RESOLUTION_MISSING",
                "The mold plan has no saved rule resolution.",
                409,
            )
        existing = resolution.handoffs.filter(handoff_type=handoff_type).first()
        if existing:
            return Response(
                {
                    "schema_version": "1.0",
                    "idempotent_replay": True,
                    **_handoff_payload(existing),
                }
            )

        contract: dict[str, object] = {
            "schema_version": "1.0",
            "mold_plan_id": str(plan.id),
            "mold_plan_resolution_id": str(resolution.id),
            "mold_revision_id": str(plan.mold_revision_id),
            "cad_artifact_version_id": (
                str(plan.cad_artifact_version_id) if plan.cad_artifact_version_id else None
            ),
            "selected_profile_id": str(resolution.selected_profile_id),
            "ruleset_checksum": resolution.ruleset_checksum,
        }
        review = None
        if handoff_type == MoldPlanHandoff.HandoffType.DESIGN_REVIEW:
            if plan.cad_artifact_version is None:
                return _error(
                    request,
                    "MOLD_PLAN_CAD_REQUIRED",
                    "Select a processed CAD version before creating a design review.",
                    409,
                )
            try:
                records = create_design_review_records(
                    plan.cad_artifact_version,
                    idempotency_key=f"mold-plan:{plan.id}:resolution:{resolution.id}:review",
                    pinned_resolution=resolution,
                )
            except DesignReviewValidationError as exc:
                return _error(request, exc.code, exc.user_message, 409)
            review = records.review
            target_ref = f"design-review:{review.id}"
            contract["review_id"] = str(review.id)
            contract["job_id"] = str(records.job.id)
            contract["ui_path"] = (
                "/engineering/design-review?deep_link_version=1.0"
                f"&target=design_review&review_id={review.id}"
            )
            if records.created:
                try:
                    run_design_review_job.apply_async(args=[str(records.job.id)], queue="cad")
                except Exception:
                    return _error(
                        request,
                        "JOB_QUEUE_UNAVAILABLE",
                        "The design review job could not be queued.",
                        503,
                    )
        else:
            routes = {
                MoldPlanHandoff.HandoffType.CAD: "/engineering/cad",
                MoldPlanHandoff.HandoffType.SIMILARITY: "/engineering/similarity",
                MoldPlanHandoff.HandoffType.CAE: "/engineering/cae",
            }
            target_ref = f"{handoff_type}:mold-plan:{plan.id}"
            contract["ui_path"] = routes[handoff_type]

        with transaction.atomic():
            locked = MoldPlan.objects.select_for_update().get(id=plan.id)
            if locked.row_version != plan.row_version:
                return _error(
                    request,
                    "CONCURRENCY_CONFLICT",
                    "The mold plan changed while the handoff was being created.",
                    409,
                )
            handoff = MoldPlanHandoff.objects.create(
                resolution=resolution,
                handoff_type=handoff_type,
                target_ref=target_ref,
                review_run=review,
                contract_snapshot=contract,
                created_by=_actor(request),
            )
            locked.row_version += 1
            locked.updated_by = _actor(request)
            locked.save(update_fields=["row_version", "updated_by", "updated_at"])
            audit_identity_event(
                "mold_plan.handoff.created.v1",
                actor_id=_actor(request),
                target_refs=[str(plan.id), str(resolution.id), target_ref],
                detail={
                    "handoff_type": handoff_type,
                    "ruleset_checksum": resolution.ruleset_checksum,
                },
            )
        return Response(
            {
                "schema_version": "1.0",
                "idempotent_replay": False,
                **_handoff_payload(handoff),
            },
            status=201,
        )


class MoldPlanProfileSelectionView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, plan_id: uuid.UUID) -> Response:
        if denied := _require(request, "rules:override"):
            return denied
        reason = str(request.data.get("reason", "")).strip()
        if not 10 <= len(reason) <= 512:
            return _error(
                request,
                "VALIDATION_OVERRIDE_REASON",
                "A specific override reason between 10 and 512 characters is required.",
                400,
            )
        if any(marker in reason.casefold() for marker in ("sk-", "api_key", "token=")):
            return _error(
                request,
                "VALIDATION_OVERRIDE_REASON_SENSITIVE",
                "Do not include credentials or tokens in an engineering override reason.",
                400,
            )
        try:
            profile_id = uuid.UUID(str(request.data.get("profile_id", "")))
        except ValueError:
            return _error(
                request,
                "VALIDATION_RULE_PROFILE",
                "profile_id must be a UUID.",
                400,
            )
        with transaction.atomic():
            plan = (
                mold_plan_queryset(request)
                .select_for_update(of=("self",))
                .filter(id=plan_id)
                .first()
            )
            if plan is None:
                return _error(request, "MOLD_PLAN_NOT_FOUND", "The mold plan is unavailable.", 404)
            if int(request.data.get("row_version", 0)) != plan.row_version:
                return _error(
                    request,
                    "CONCURRENCY_CONFLICT",
                    "The mold plan changed after it was loaded.",
                    409,
                )
            if plan.status in {MoldPlan.Status.COMPLETED, MoldPlan.Status.ARCHIVED}:
                return _error(
                    request,
                    "MOLD_PLAN_IMMUTABLE",
                    "Reopen a completed or archived plan before changing its rule set.",
                    409,
                )
            context = {item.dimension: item.value_code for item in plan.context_entries.all()}
            try:
                automatic = resolve_rule_profile_for_context(
                    context,
                    scope=plan.scope,
                    classification=plan.classification,
                )
            except RuleResolutionError as exc:
                return _error(request, exc.code, exc.user_message, 409)
            candidate = next(
                (
                    item
                    for item in automatic.snapshot["candidates"]
                    if str(item["profile_id"]) == str(profile_id)
                ),
                None,
            )
            if candidate is None:
                return _error(
                    request,
                    "RULE_PROFILE_OVERRIDE_NOT_ELIGIBLE",
                    "Only a profile eligible for the saved engineering context can be selected.",
                    409,
                )
            profile = RuleProfile.objects.prefetch_related("rules").get(id=profile_id)
            record = MoldPlanResolution.objects.create(
                plan=plan,
                resolution_number=plan.resolutions.count() + 1,
                context_checksum=_context_checksum(context),
                selected_profile=profile,
                ruleset_checksum=profile.ruleset_checksum,
                applicability_checksum=candidate["applicability_checksum"],
                selection_mode="manual_override",
                reason=(
                    f"Authorized manual selection of {profile.profile_key}@{profile.version} "
                    "from the eligible candidate set."
                ),
                override_reason=reason,
                context_snapshot=context,
                candidate_snapshot=automatic.snapshot["candidates"],
                exclusion_summary=automatic.snapshot.get("excluded_summary", []),
                resolved_by=_actor(request),
            )
            _create_requirements(record)
            plan.status = MoldPlan.Status.READY
            plan.updated_by = _actor(request)
            plan.row_version += 1
            plan.save(update_fields=["status", "updated_by", "row_version", "updated_at"])
            audit_identity_event(
                "mold_plan.profile_overridden.v1",
                actor_id=_actor(request),
                target_refs=[str(plan.id), str(record.id), str(profile.id)],
                detail={
                    "reason": reason,
                    "eligible_candidate_count": len(automatic.snapshot["candidates"]),
                    "automatic_profile_id": str(automatic.profile.id),
                },
            )
        return Response(mold_plan_payload(mold_plan_queryset(request).get(id=plan.id), detail=True))


class MoldPlanActionView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, plan_id: uuid.UUID) -> Response:
        action = str(request.data.get("action", ""))
        permission = (
            "mold-planning:manage" if action in {"reopen", "archive"} else "mold-planning:complete"
        )
        if denied := _require(request, permission):
            return denied
        reason = str(request.data.get("reason", "")).strip()
        if not 3 <= len(reason) <= 512:
            return _error(
                request,
                "VALIDATION_REASON_REQUIRED",
                "A reason between 3 and 512 characters is required.",
                400,
            )
        transitions = {
            MoldPlan.Status.DRAFT: {"archive": MoldPlan.Status.ARCHIVED},
            MoldPlan.Status.READY: {
                "complete": MoldPlan.Status.COMPLETED,
                "archive": MoldPlan.Status.ARCHIVED,
            },
            MoldPlan.Status.COMPLETED: {"reopen": MoldPlan.Status.DRAFT},
            MoldPlan.Status.ARCHIVED: {"reopen": MoldPlan.Status.DRAFT},
        }
        with transaction.atomic():
            plan = (
                mold_plan_queryset(request)
                .select_for_update(of=("self",))
                .filter(id=plan_id)
                .first()
            )
            if plan is None:
                return _error(request, "MOLD_PLAN_NOT_FOUND", "The mold plan is unavailable.", 404)
            if int(request.data.get("row_version", 0)) != plan.row_version:
                return _error(
                    request,
                    "CONCURRENCY_CONFLICT",
                    "The mold plan changed after it was loaded.",
                    409,
                )
            target = transitions.get(plan.status, {}).get(action)
            if target is None:
                return _error(
                    request,
                    "INVALID_MOLD_PLAN_TRANSITION",
                    f"Cannot {action} a {plan.status} plan.",
                    409,
                )
            previous = plan.status
            plan.status = target
            plan.archived_at = timezone.now() if target == MoldPlan.Status.ARCHIVED else None
            plan.archive_reason = reason if target == MoldPlan.Status.ARCHIVED else ""
            plan.updated_by = _actor(request)
            plan.row_version += 1
            plan.save(
                update_fields=[
                    "status",
                    "archived_at",
                    "archive_reason",
                    "updated_by",
                    "row_version",
                    "updated_at",
                ]
            )
            audit_identity_event(
                f"mold_plan.{action}.v1",
                actor_id=_actor(request),
                target_refs=[str(plan.id)],
                detail={"from": previous, "to": target, "reason": reason},
            )
        return Response(mold_plan_payload(mold_plan_queryset(request).get(id=plan.id), detail=True))
