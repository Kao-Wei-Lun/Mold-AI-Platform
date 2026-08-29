from __future__ import annotations

import hashlib
import json
import re

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
from .models import KnowledgeDocument, RuleProfile, RuleVersion

VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
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


class RuleProfileGovernanceListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        get_demo_rule_profile()
        profiles = RuleProfile.objects.prefetch_related("rules").order_by(
            "profile_key", "-created_at"
        )
        return Response(
            {
                "schema_version": "1.0",
                "items": [rule_profile_payload(profile) for profile in profiles],
            }
        )

    def post(self, request: Request) -> Response:
        if denied := _require(request, "rules:author"):
            return denied
        if request.data.get("action") != "clone":
            return _error(request, "VALIDATION_ACTION", "Only clone is supported.", 400)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        source = (
            RuleProfile.objects.prefetch_related("rules")
            .filter(id=request.data.get("source_profile_id"))
            .first()
        )
        if source is None:
            return _error(request, "NOT_FOUND", "Source rule profile not found.", 404)
        version = str(request.data.get("version", "")).strip()
        if not VERSION_RE.fullmatch(version):
            return _error(request, "VALIDATION_VERSION", "A valid version is required.", 400)
        actor = _actor(request)
        try:
            with transaction.atomic():
                clone = RuleProfile.objects.create(
                    profile_key=source.profile_key,
                    version=version,
                    status="draft",
                    workflow_status=RuleProfile.WorkflowStatus.DRAFT,
                    product_scope=source.product_scope,
                    material_scope=source.material_scope,
                    owner=actor,
                    approved_by="",
                    ruleset_checksum=source.ruleset_checksum,
                    change_summary=str(request.data.get("change_summary", "")).strip(),
                )
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
                audit_identity_event(
                    "rule_profile.cloned.v1",
                    actor_id=actor,
                    target_refs=[f"rule-profile:{clone.id}", f"rule-profile:{source.id}"],
                    detail={"version": version, "reason": reason},
                )
        except IntegrityError:
            return _error(
                request, "RULE_PROFILE_VERSION_CONFLICT", "This profile version exists.", 409
            )
        clone = RuleProfile.objects.prefetch_related("rules").get(id=clone.id)
        return Response(rule_profile_payload(clone), status=201)


class RuleProfileWorkflowView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, profile_id: str) -> Response:
        profile = RuleProfile.objects.prefetch_related("rules").filter(id=profile_id).first()
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
            issues = []
            if not profile.rules.exists():
                issues.append("RULESET_EMPTY")
            for rule in profile.rules.all():
                if rule.evaluator not in EVALUATORS:
                    issues.append(f"EVALUATOR_UNREGISTERED:{rule.rule_id}")
                if rule.operator not in {"lte", "gte", "eq"}:
                    issues.append(f"OPERATOR_UNSUPPORTED:{rule.rule_id}")
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
        profile = RuleProfile.objects.prefetch_related("rules").filter(id=profile_id).first()
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
            profile.ruleset_checksum = _rule_checksum(profile)
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
                change = (
                    "added" if before is None else "removed" if after is None else "modified"
                )
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
