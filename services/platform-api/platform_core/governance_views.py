from __future__ import annotations

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
