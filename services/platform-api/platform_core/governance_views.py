from __future__ import annotations

import hashlib
import json
import re
from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .contracts import rule_profile_payload
from .design_review import EVALUATORS, get_demo_rule_profile
from .identity import audit_identity_event
from .knowledge import knowledge_document_payload
from .models import (
    Artifact,
    DataScope,
    KnowledgeDocument,
    MasterDataItem,
    Mold,
    MoldRevision,
    Project,
    ReviewRun,
    RuleProfile,
    RuleProfileApplicability,
    RuleVersion,
)
from .pagination import PaginationValueError, paginate
from .rule_resolution import applicability_checksum

VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
PROFILE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,127}$")
KNOWLEDGE_TRANSITIONS = {
    "draft": {"submit": "in_review", "retire": "retired"},
    "in_review": {"approve": "approved", "retire": "retired"},
    "approved": {"publish": "published", "retire": "retired"},
    "published": {"retire": "retired"},
    "retired": {},
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


def _require(request: Request, permission: str) -> Response | None:
    if permission in getattr(request._request, "mold_ai_permissions", set()):
        return None
    return _error(request, "ACCESS_DENIED", f"The account does not grant {permission}.", 403)


def _actor(request: Request) -> str:
    return str(getattr(request._request, "mold_ai_actor_id", "anonymous"))


def _reason(request: Request) -> tuple[str, Response | None]:
    reason = str(request.data.get("reason", "")).strip()
    if not reason:
        return "", _error(request, "VALIDATION_REASON_REQUIRED", "A reason is required.", 400)
    return reason[:512], None


def _rule_validation_issues(profile: RuleProfile) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    enabled_rules = list(profile.rules.filter(enabled=True))
    if not enabled_rules:
        issues.append(
            {"code": "RULESET_EMPTY", "message": "At least one enabled rule is required."}
        )
    seen: set[str] = set()
    for rule in enabled_rules:
        if rule.rule_id in seen:
            issues.append(
                {
                    "code": "RULE_ID_DUPLICATE",
                    "rule_id": rule.rule_id,
                    "message": "Rule ID must be unique.",
                }
            )
        seen.add(rule.rule_id)
        if rule.evaluator not in EVALUATORS:
            issues.append(
                {
                    "code": "EVALUATOR_UNREGISTERED",
                    "rule_id": rule.rule_id,
                    "message": "Evaluator is not registered.",
                }
            )
        if rule.operator not in {"lte", "gte", "eq"}:
            issues.append(
                {
                    "code": "OPERATOR_UNSUPPORTED",
                    "rule_id": rule.rule_id,
                    "message": "Operator is not supported.",
                }
            )
        if not rule.title.strip():
            issues.append(
                {
                    "code": "TITLE_REQUIRED",
                    "rule_id": rule.rule_id,
                    "message": "Rule title is required.",
                }
            )
        if not rule.unit.strip():
            issues.append(
                {
                    "code": "UNIT_REQUIRED",
                    "rule_id": rule.rule_id,
                    "message": "Rule unit is required.",
                }
            )
        reference = rule.reference if isinstance(rule.reference, dict) else {}
        if (
            not str(reference.get("document", "")).strip()
            or not str(reference.get("revision", "")).strip()
        ):
            issues.append(
                {
                    "code": "REFERENCE_REQUIRED",
                    "rule_id": rule.rule_id,
                    "message": "Reference document and revision are required.",
                }
            )
    return issues


class RuleProfileGovernanceListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        get_demo_rule_profile()
        profiles = (
            RuleProfile.objects.select_related("scope")
            .prefetch_related("rules", "applicability_entries")
            .order_by("profile_key", "-created_at")
        )
        if workflow_status := request.query_params.get("status"):
            profiles = profiles.filter(workflow_status=workflow_status)
        try:
            records, page = paginate(
                request,
                profiles,
                allowed_sort={
                    "profile_key": "profile_key",
                    "created_at": "created_at",
                    "workflow_status": "workflow_status",
                },
                default_sort="-created_at",
            )
        except PaginationValueError as exc:
            return _error(request, "VALIDATION_PAGINATION", str(exc), 400)
        return Response(
            {
                "schema_version": "1.0",
                "items": [rule_profile_payload(profile) for profile in records],
                "page": page,
            }
        )

    def post(self, request: Request) -> Response:
        if denied := _require(request, "rules:author"):
            return denied
        action = str(request.data.get("action", "clone"))
        if action not in {"blank", "template", "clone"}:
            return _error(
                request,
                "VALIDATION_ACTION",
                "action must be blank, template, or clone.",
                400,
            )
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        source = None
        if action != "blank":
            source = (
                RuleProfile.objects.select_related("scope")
                .prefetch_related("rules", "applicability_entries")
                .filter(id=request.data.get("source_profile_id"))
                .first()
            )
            if source is None:
                return _error(request, "NOT_FOUND", "Source rule profile not found.", 404)
            if action == "template" and source.workflow_status not in {
                RuleProfile.WorkflowStatus.PUBLISHED,
                RuleProfile.WorkflowStatus.RETIRED,
            }:
                return _error(
                    request,
                    "RULE_TEMPLATE_NOT_GOVERNED",
                    "A template must come from a published or retired profile.",
                    409,
                )
        version = str(request.data.get("version", "")).strip()
        if not VERSION_RE.fullmatch(version):
            return _error(request, "VALIDATION_VERSION", "A valid version is required.", 400)
        profile_key = str(
            request.data.get("profile_key", source.profile_key if source else "")
        ).strip()
        if not PROFILE_KEY_RE.fullmatch(profile_key):
            return _error(
                request, "VALIDATION_PROFILE_KEY", "A valid profile key is required.", 400
            )
        actor = _actor(request)
        try:
            with transaction.atomic():
                clone = RuleProfile.objects.create(
                    profile_key=profile_key,
                    version=version,
                    status="draft",
                    workflow_status=RuleProfile.WorkflowStatus.DRAFT,
                    product_scope=source.product_scope if source else [],
                    material_scope=source.material_scope if source else [],
                    priority=source.priority if source else 0,
                    is_default=False,
                    effective_from=source.effective_from if source else None,
                    effective_to=source.effective_to if source else None,
                    scope=(
                        source.scope
                        if source
                        else DataScope.objects.filter(code="public-demo", is_active=True).first()
                    ),
                    classification=source.classification if source else "public_demo",
                    resolution_status=RuleProfile.ResolutionStatus.ELIGIBLE,
                    owner=actor,
                    approved_by="",
                    ruleset_checksum=source.ruleset_checksum
                    if source
                    else hashlib.sha256(b"[]").hexdigest(),
                    change_summary=str(request.data.get("change_summary", "")).strip(),
                )
                if source:
                    RuleVersion.objects.bulk_create(
                        [
                            RuleVersion(
                                profile=clone,
                                rule_id=rule.rule_id,
                                rule_version=version,
                                title=rule.title,
                                description=rule.description,
                                evaluator=rule.evaluator,
                                applicability=rule.applicability,
                                parameters=rule.parameters,
                                operator=rule.operator,
                                limit_value=rule.limit_value,
                                unit=rule.unit,
                                tolerance=rule.tolerance,
                                severity=rule.severity,
                                risk_type=rule.risk_type,
                                recommendation=rule.recommendation,
                                reference=rule.reference,
                                sort_order=rule.sort_order,
                                enabled=rule.enabled,
                            )
                            for rule in source.rules.all()
                        ]
                    )
                    RuleProfileApplicability.objects.bulk_create(
                        [
                            RuleProfileApplicability(
                                profile=clone,
                                dimension=item.dimension,
                                value_code=item.value_code,
                                match_mode=item.match_mode,
                            )
                            for item in source.applicability_entries.all()
                        ]
                    )
                clone.applicability_checksum = applicability_checksum(clone)
                clone.save(update_fields=["applicability_checksum"])
                audit_identity_event(
                    f"rule_profile.{action}_created.v1",
                    actor_id=actor,
                    target_refs=[
                        f"rule-profile:{clone.id}",
                        *([f"rule-profile:{source.id}"] if source else []),
                    ],
                    detail={"version": version, "reason": reason, "creation_mode": action},
                )
        except IntegrityError:
            return _error(
                request, "RULE_PROFILE_VERSION_CONFLICT", "This profile version exists.", 409
            )
        clone = (
            RuleProfile.objects.select_related("scope")
            .prefetch_related("rules", "applicability_entries")
            .get(id=clone.id)
        )
        return Response(rule_profile_payload(clone), status=201)


class RuleProfileWorkflowView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, profile_id: str) -> Response:
        profile = (
            RuleProfile.objects.select_related("scope")
            .prefetch_related("rules", "applicability_entries")
            .filter(id=profile_id)
            .first()
        )
        if profile is None:
            return _error(request, "NOT_FOUND", "Rule profile not found.", 404)
        action = str(request.data.get("action", "")).strip()
        permission = (
            "rules:approve" if action in {"approve", "publish", "retire"} else "rules:author"
        )
        if denied := _require(request, permission):
            return denied
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if int(request.data.get("row_version", 0)) != profile.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "Rule profile changed.", 409)

        transitions = {
            RuleProfile.WorkflowStatus.DRAFT: {"test": RuleProfile.WorkflowStatus.VALIDATED},
            RuleProfile.WorkflowStatus.VALIDATED: {"submit": RuleProfile.WorkflowStatus.IN_REVIEW},
            RuleProfile.WorkflowStatus.IN_REVIEW: {"approve": RuleProfile.WorkflowStatus.APPROVED},
            RuleProfile.WorkflowStatus.APPROVED: {"publish": RuleProfile.WorkflowStatus.PUBLISHED},
            RuleProfile.WorkflowStatus.PUBLISHED: {"retire": RuleProfile.WorkflowStatus.RETIRED},
            RuleProfile.WorkflowStatus.RETIRED: {},
        }
        next_status = transitions.get(profile.workflow_status, {}).get(action)
        if next_status is None:
            return _error(request, "INVALID_STATE_TRANSITION", "Rule transition is invalid.", 409)
        actor = _actor(request)
        if action == "approve" and actor == profile.owner:
            return _error(
                request,
                "SEGREGATION_OF_DUTIES",
                "The rule author cannot approve the same profile version.",
                409,
            )
        if action == "test":
            issues = _rule_validation_issues(profile)
            if issues:
                return _error(
                    request,
                    "RULE_VALIDATION_FAILED",
                    "The rule profile failed deterministic validation.",
                    409,
                    issues=issues,
                )

        with transaction.atomic():
            if action == "submit":
                profile.submitted_by = actor
            elif action == "approve":
                profile.reviewed_by = actor
                profile.approved_by = actor
            elif action == "publish":
                RuleProfile.objects.filter(
                    profile_key=profile.profile_key,
                    workflow_status=RuleProfile.WorkflowStatus.PUBLISHED,
                ).exclude(id=profile.id).update(
                    workflow_status=RuleProfile.WorkflowStatus.RETIRED,
                    status="retired",
                    retired_at=timezone.now(),
                )
                profile.status = "approved_demo"
                profile.published_at = timezone.now()
            elif action == "retire":
                profile.status = "retired"
                profile.retired_at = timezone.now()
            profile.workflow_status = next_status
            profile.row_version += 1
            profile.save()
            audit_identity_event(
                f"rule_profile.{action}.v1",
                actor_id=actor,
                target_refs=[f"rule-profile:{profile.id}"],
                detail={"reason": reason, "workflow_status": next_status},
            )
        return Response(rule_profile_payload(profile))


class RuleProfileValidationView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, profile_id: str) -> Response:
        if denied := _require(request, "rules:author"):
            return denied
        profile = RuleProfile.objects.prefetch_related("rules").filter(id=profile_id).first()
        if profile is None:
            return _error(request, "NOT_FOUND", "Rule profile not found.", 404)
        issues = _rule_validation_issues(profile)
        return Response(
            {
                "schema_version": "1.0",
                "profile_id": str(profile.id),
                "valid": not issues,
                "issues": issues,
                "ruleset_checksum": profile.ruleset_checksum,
            }
        )


class RuleProfileImpactPreviewView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, profile_id: str) -> Response:
        if denied := _require(request, "rules:author"):
            return denied
        profile = RuleProfile.objects.select_related("scope").filter(id=profile_id).first()
        if profile is None:
            return _error(request, "NOT_FOUND", "Rule profile not found.", 404)
        mold_scope = Mold.objects.all()
        revision_scope = MoldRevision.objects.all()
        cad_scope = Artifact.objects.filter(kind=Artifact.Kind.CAD_SOURCE)
        if profile.scope_id:
            mold_scope = mold_scope.filter(project__scope=profile.scope)
            revision_scope = revision_scope.filter(mold__project__scope=profile.scope)
            cad_scope = cad_scope.filter(mold_revision__mold__project__scope=profile.scope)
        return Response(
            {
                "schema_version": "1.0",
                "profile_id": str(profile.id),
                "impact": {
                    "molds": mold_scope.count(),
                    "revisions": revision_scope.count(),
                    "cad_artifacts": cad_scope.count(),
                    "historical_reviews": ReviewRun.objects.filter(profile=profile).count(),
                },
                "note": "Counts are a governed scope preview; historical reviews remain immutable.",
            }
        )


def _rule_checksum(profile: RuleProfile) -> str:
    content = [
        {
            "rule_id": item.rule_id,
            "rule_version": item.rule_version,
            "title": item.title,
            "description": item.description,
            "evaluator": item.evaluator,
            "applicability": item.applicability,
            "parameters": item.parameters,
            "operator": item.operator,
            "limit_value": item.limit_value,
            "unit": item.unit,
            "tolerance": item.tolerance,
            "severity": item.severity,
            "risk_type": item.risk_type,
            "recommendation": item.recommendation,
            "reference": item.reference,
            "enabled": item.enabled,
        }
        for item in profile.rules.order_by("sort_order", "rule_id")
    ]
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class RuleProfileDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, profile_id: str) -> Response:
        profile = (
            RuleProfile.objects.select_related("scope")
            .prefetch_related("rules", "applicability_entries")
            .filter(id=profile_id)
            .first()
        )
        if profile is None:
            return _error(request, "NOT_FOUND", "Rule profile not found.", 404)
        return Response(rule_profile_payload(profile))

    def patch(self, request: Request, profile_id: str) -> Response:
        if denied := _require(request, "rules:author"):
            return denied
        profile = RuleProfile.objects.prefetch_related("rules").filter(id=profile_id).first()
        if profile is None:
            return _error(request, "NOT_FOUND", "Rule profile not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if profile.workflow_status != RuleProfile.WorkflowStatus.DRAFT:
            return _error(
                request,
                "PUBLISHED_CONTENT_IMMUTABLE",
                "Clone a governed profile before editing rule content.",
                409,
            )
        if int(request.data.get("row_version", 0)) != profile.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "Rule profile changed.", 409)
        rules = request.data.get("rules")
        if not isinstance(rules, list) or not 1 <= len(rules) <= 100:
            return _error(request, "VALIDATION_RULES", "rules must contain 1-100 items.", 400)
        normalized: list[dict[str, object]] = []
        seen: set[str] = set()
        try:
            for index, item in enumerate(rules):
                if not isinstance(item, dict):
                    raise ValueError("Each rule must be an object.")
                rule_id = str(item.get("rule_id", "")).strip()
                evaluator = str(item.get("evaluator", "")).strip()
                condition = item.get("condition", {})
                if not VERSION_RE.fullmatch(rule_id) or evaluator not in EVALUATORS:
                    raise ValueError("Rule ID or evaluator is invalid.")
                if rule_id in seen or not isinstance(condition, dict):
                    raise ValueError("Rule IDs must be unique and condition must be an object.")
                operator = str(condition.get("operator", ""))
                if operator not in {"lte", "gte", "eq"}:
                    raise ValueError("Rule operator is unsupported.")
                seen.add(rule_id)
                normalized.append(
                    {
                        "rule_id": rule_id,
                        "title": str(item.get("title", "")).strip(),
                        "description": str(item.get("description", "")).strip(),
                        "evaluator": evaluator,
                        "applicability": item.get("applicability", {}),
                        "parameters": item.get("measurement_definition", {}),
                        "operator": operator,
                        "limit_value": condition.get("limit"),
                        "unit": str(condition.get("unit", ""))[:32],
                        "tolerance": float(condition.get("tolerance", 0)),
                        "severity": str(item.get("severity", "medium"))[:16],
                        "risk_type": str(item.get("risk_type", ""))[:64],
                        "recommendation": str(item.get("recommendation", "")),
                        "reference": item.get("reference", {}),
                        "enabled": bool(item.get("enabled", True)),
                        "sort_order": index,
                    }
                )
        except (TypeError, ValueError) as exc:
            return _error(request, "VALIDATION_RULES", str(exc), 400)
        normalized_applicability: list[tuple[str, str, str]] | None = None
        applicability = request.data.get("applicability")
        if applicability is not None:
            if not isinstance(applicability, list) or len(applicability) > 100:
                return _error(
                    request,
                    "VALIDATION_APPLICABILITY",
                    "applicability must be a list of at most 100 items.",
                    400,
                )
            normalized_applicability = []
            seen_applicability: set[tuple[str, str, str]] = set()
            for item in applicability:
                if not isinstance(item, dict):
                    return _error(
                        request,
                        "VALIDATION_APPLICABILITY",
                        "Each applicability item must be an object.",
                        400,
                    )
                entry = (
                    str(item.get("dimension", "")),
                    str(item.get("value_code", "")).strip(),
                    str(item.get("match_mode", "include")),
                )
                if (
                    entry[0] not in RuleProfileApplicability.Dimension.values
                    or not entry[1]
                    or entry[2] not in RuleProfileApplicability.MatchMode.values
                    or entry in seen_applicability
                ):
                    return _error(
                        request,
                        "VALIDATION_APPLICABILITY",
                        "Applicability contains an invalid or duplicate entry.",
                        400,
                    )
                seen_applicability.add(entry)
                kind_by_dimension = {
                    "mold_type": MasterDataItem.Kind.MOLD_TYPE,
                    "product_type": MasterDataItem.Kind.PRODUCT_TYPE,
                    "material": MasterDataItem.Kind.MATERIAL,
                    "molding_process": MasterDataItem.Kind.MOLDING_PROCESS,
                    "location": MasterDataItem.Kind.LOCATION,
                }
                if entry[0] == "project":
                    exists = Project.objects.filter(
                        scope=profile.scope, code=entry[1], status=Project.Status.ACTIVE
                    ).exists()
                else:
                    exists = MasterDataItem.objects.filter(
                        scope=profile.scope,
                        kind=kind_by_dimension[entry[0]],
                        code=entry[1],
                        status=MasterDataItem.Status.ACTIVE,
                    ).exists()
                if not exists:
                    return _error(
                        request,
                        "VALIDATION_APPLICABILITY_REFERENCE",
                        f"Unknown active {entry[0]} reference: {entry[1]}.",
                        400,
                    )
                normalized_applicability.append(entry)
        try:
            priority = int(request.data.get("priority", profile.priority))
        except (TypeError, ValueError):
            return _error(request, "VALIDATION_PRIORITY", "priority must be an integer.", 400)
        resolution_status = str(request.data.get("resolution_status", profile.resolution_status))
        if resolution_status not in RuleProfile.ResolutionStatus.values:
            return _error(
                request,
                "VALIDATION_RESOLUTION_STATUS",
                "Invalid resolution status.",
                400,
            )
        try:
            effective_from = profile.effective_from
            effective_to = profile.effective_to
            if "effective_from" in request.data:
                effective_from = (
                    date.fromisoformat(str(request.data["effective_from"]))
                    if request.data.get("effective_from")
                    else None
                )
            if "effective_to" in request.data:
                effective_to = (
                    date.fromisoformat(str(request.data["effective_to"]))
                    if request.data.get("effective_to")
                    else None
                )
        except ValueError:
            return _error(
                request,
                "VALIDATION_EFFECTIVE_PERIOD",
                "Effective dates must use YYYY-MM-DD.",
                400,
            )
        if effective_from and effective_to and effective_from > effective_to:
            return _error(
                request,
                "VALIDATION_EFFECTIVE_PERIOD",
                "effective_from must not be after effective_to.",
                400,
            )
        with transaction.atomic():
            existing = {item.rule_id: item for item in profile.rules.all()}
            for values in normalized:
                rule_id = str(values["rule_id"])
                rule = existing.pop(rule_id, None)
                if rule is None:
                    rule = RuleVersion(
                        profile=profile, rule_id=rule_id, rule_version=profile.version
                    )
                for field, value in values.items():
                    setattr(rule, field, value)
                rule.rule_version = profile.version
                rule.save()
            for removed in existing.values():
                removed.enabled = False
                removed.save(update_fields=["enabled"])
            profile.change_summary = str(
                request.data.get("change_summary", profile.change_summary)
            ).strip()
            if isinstance(request.data.get("product_scope"), list):
                profile.product_scope = request.data["product_scope"]
            if isinstance(request.data.get("material_scope"), list):
                profile.material_scope = request.data["material_scope"]
            profile.priority = priority
            if "is_default" in request.data:
                profile.is_default = bool(request.data["is_default"])
            profile.resolution_status = resolution_status
            profile.effective_from = effective_from
            profile.effective_to = effective_to
            if normalized_applicability is not None:
                profile.applicability_entries.all().delete()
                RuleProfileApplicability.objects.bulk_create(
                    [
                        RuleProfileApplicability(
                            profile=profile,
                            dimension=dimension,
                            value_code=value_code,
                            match_mode=match_mode,
                        )
                        for dimension, value_code, match_mode in normalized_applicability
                    ]
                )
            profile.ruleset_checksum = _rule_checksum(profile)
            profile.applicability_checksum = applicability_checksum(profile)
            profile.row_version += 1
            profile.save()
            audit_identity_event(
                "rule_profile.updated.v1",
                actor_id=_actor(request),
                target_refs=[f"rule-profile:{profile.id}"],
                detail={"reason": reason, "rule_count": len(normalized)},
            )
        return Response(rule_profile_payload(profile))


class RuleProfileDiffView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, profile_id: str) -> Response:
        current = RuleProfile.objects.prefetch_related("rules").filter(id=profile_id).first()
        baseline = (
            RuleProfile.objects.prefetch_related("rules")
            .filter(id=request.query_params.get("against"))
            .first()
        )
        if current is None or baseline is None:
            return _error(request, "NOT_FOUND", "Rule profile comparison target not found.", 404)
        fields = (
            "title",
            "description",
            "evaluator",
            "applicability",
            "parameters",
            "operator",
            "limit_value",
            "unit",
            "tolerance",
            "severity",
            "risk_type",
            "recommendation",
            "reference",
            "enabled",
        )
        left = {item.rule_id: item for item in baseline.rules.all()}
        right = {item.rule_id: item for item in current.rules.all()}
        changes = []
        for rule_id in sorted(set(left) | set(right)):
            before, after = left.get(rule_id), right.get(rule_id)
            changed_fields = [
                field
                for field in fields
                if getattr(before, field, None) != getattr(after, field, None)
            ]
            if before is None or after is None or changed_fields:
                change = "added" if before is None else "removed" if after is None else "modified"
                changes.append(
                    {
                        "rule_id": rule_id,
                        "change": change,
                        "changed_fields": changed_fields,
                    }
                )
        return Response(
            {
                "schema_version": "1.0",
                "baseline_profile_id": str(baseline.id),
                "profile_id": str(current.id),
                "changes": changes,
            }
        )


class KnowledgeDocumentWorkflowView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, document_id: str) -> Response:
        document = (
            KnowledgeDocument.objects.select_related("artifact_version__artifact")
            .filter(id=document_id)
            .first()
        )
        if document is None:
            return _error(request, "NOT_FOUND", "Knowledge document not found.", 404)
        action = str(request.data.get("action", "")).strip()
        permission = (
            "knowledge:approve"
            if action in {"approve", "publish", "retire"}
            else "knowledge:author"
        )
        if denied := _require(request, permission):
            return denied
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if int(request.data.get("row_version", 0)) != document.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "Knowledge document changed.", 409)
        next_status = KNOWLEDGE_TRANSITIONS.get(document.publication_status, {}).get(action)
        if next_status is None:
            return _error(
                request, "INVALID_STATE_TRANSITION", "Knowledge transition is invalid.", 409
            )
        actor = _actor(request)
        if action == "approve" and actor == document.owner:
            return _error(
                request,
                "SEGREGATION_OF_DUTIES",
                "The knowledge author cannot approve the same document version.",
                409,
            )
        if action == "publish":
            if document.ingestion_status != KnowledgeDocument.IngestionStatus.INDEXED:
                return _error(
                    request,
                    "KNOWLEDGE_NOT_INDEXED",
                    "Only a successfully indexed document can be published.",
                    409,
                )
            if document.injection_scan_status != "clear":
                return _error(
                    request,
                    "KNOWLEDGE_QUARANTINED",
                    "A document with injection findings cannot be published.",
                    409,
                )
        with transaction.atomic():
            if action == "submit":
                document.submitted_by = actor
            elif action == "approve":
                document.reviewed_by = actor
                document.approved_by = actor
            elif action == "publish":
                KnowledgeDocument.objects.filter(
                    document_key=document.document_key, publication_status="published"
                ).exclude(id=document.id).update(
                    publication_status="retired", retired_at=timezone.now()
                )
                document.published_at = timezone.now()
            elif action == "retire":
                document.retired_at = timezone.now()
            document.publication_status = next_status
            document.row_version += 1
            document.save()
            audit_identity_event(
                f"knowledge_document.{action}.v1",
                actor_id=actor,
                target_refs=[f"knowledge-document:{document.id}"],
                detail={"reason": reason, "publication_status": next_status},
            )
        return Response(knowledge_document_payload(document))
