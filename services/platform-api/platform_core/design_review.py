import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from .models import (
    ArtifactVersion,
    AuditEvent,
    CADModel,
    DataScope,
    Job,
    JobEvent,
    MoldPlanResolution,
    ReviewDecision,
    ReviewFinding,
    ReviewRun,
    RuleProfile,
    RuleVersion,
)
from .rule_resolution import RuleResolutionError, applicability_checksum, resolve_rule_profile

PROFILE_KEY = "demo-general-design@1.0"
CAPABILITY_ID = "mold.design_review"
CAPABILITY_VERSION = "1.0.0"
ALLOWED_CONTEXT_KEYS = {
    "nominal_wall_thickness_mm",
    "max_rib_thickness_mm",
    "minimum_draft_angle_deg",
}


class DesignReviewValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


@dataclass(frozen=True)
class DesignReviewRecords:
    review: ReviewRun
    job: Job
    created: bool


@dataclass(frozen=True)
class Evaluation:
    result: str
    actual_value: float | None
    message: str
    geometry_location: dict[str, object]
    evidence_refs: list[str]
    quality_flags: list[str]


def _rule_specs() -> list[dict[str, object]]:
    return [
        {
            "rule_id": "DEMO-BBOX-MAX-001",
            "title": "Maximum overall dimension",
            "description": "Checks the largest model bounding-box dimension.",
            "evaluator": "bbox_dimension",
            "parameters": {"aggregation": "max"},
            "operator": "lte",
            "limit_value": 25.0,
            "unit": "mm",
            "severity": "high",
            "risk_type": "machine_envelope",
            "recommendation": "Confirm the intended Demo envelope or revise the geometry.",
        },
        {
            "rule_id": "DEMO-BBOX-MIN-002",
            "title": "Minimum overall dimension",
            "description": "Checks the smallest model bounding-box dimension.",
            "evaluator": "bbox_dimension",
            "parameters": {"aggregation": "min"},
            "operator": "gte",
            "limit_value": 2.0,
            "unit": "mm",
            "severity": "medium",
            "risk_type": "manufacturability",
            "recommendation": "Review very small overall dimensions and source units.",
        },
        {
            "rule_id": "DEMO-ASPECT-003",
            "title": "Bounding-box aspect ratio",
            "description": "Limits the ratio between largest and smallest bounding-box dimensions.",
            "evaluator": "bbox_aspect_ratio",
            "operator": "lte",
            "limit_value": 4.0,
            "unit": "ratio",
            "severity": "medium",
            "risk_type": "part_geometry",
            "recommendation": "Review the long/slender geometry and handling assumptions.",
        },
        {
            "rule_id": "DEMO-VOLUME-MIN-004",
            "title": "Minimum solid volume",
            "description": "Checks aggregate solid volume when physical units are known.",
            "evaluator": "cad_scalar",
            "parameters": {"field": "volume", "location": "solid:aggregate"},
            "operator": "gte",
            "limit_value": 100.0,
            "unit": "mm^3",
            "severity": "medium",
            "risk_type": "data_quality",
            "recommendation": "Confirm model scale, units, and solid validity.",
        },
        {
            "rule_id": "DEMO-SURFACE-MAX-005",
            "title": "Maximum aggregate surface area",
            "description": "Checks aggregate surface area when physical units are known.",
            "evaluator": "cad_scalar",
            "parameters": {"field": "surface_area", "location": "surface:aggregate"},
            "operator": "lte",
            "limit_value": 10000.0,
            "unit": "mm^2",
            "severity": "low",
            "risk_type": "complexity",
            "recommendation": "Review model scale and surface complexity.",
        },
        {
            "rule_id": "DEMO-FACE-MAX-006",
            "title": "Maximum face count",
            "description": "Limits topology face count for the Demo processing profile.",
            "evaluator": "cad_scalar",
            "parameters": {"field": "face_count", "location": "model:topology-summary"},
            "operator": "lte",
            "limit_value": 5000.0,
            "unit": "count",
            "severity": "low",
            "risk_type": "processing_complexity",
            "recommendation": "Simplify nonessential topology for the Demo workflow.",
        },
        {
            "rule_id": "DEMO-EDGE-MAX-007",
            "title": "Maximum edge count",
            "description": "Limits topology edge count for the Demo processing profile.",
            "evaluator": "cad_scalar",
            "parameters": {"field": "edge_count", "location": "model:topology-summary"},
            "operator": "lte",
            "limit_value": 10000.0,
            "unit": "count",
            "severity": "low",
            "risk_type": "processing_complexity",
            "recommendation": "Simplify nonessential topology for the Demo workflow.",
        },
        {
            "rule_id": "DEMO-EDGE-FACE-008",
            "title": "Maximum edge-to-face ratio",
            "description": "Checks a global topology complexity ratio.",
            "evaluator": "edge_face_ratio",
            "operator": "lte",
            "limit_value": 4.0,
            "unit": "ratio",
            "severity": "low",
            "risk_type": "topology_quality",
            "recommendation": "Inspect fragmented or unusually complex topology.",
        },
        {
            "rule_id": "DEMO-OPEN-SHELL-009",
            "title": "Open-shell quality flag absent",
            "description": "Fails when the deterministic geometry parser reports an open shell.",
            "evaluator": "quality_flag_absent",
            "parameters": {"flag": "OPEN_SHELL"},
            "operator": "eq",
            "limit_value": 0.0,
            "unit": "boolean",
            "severity": "high",
            "risk_type": "geometry_integrity",
            "recommendation": "Repair the shell before downstream engineering analysis.",
        },
        {
            "rule_id": "DEMO-UNIT-010",
            "title": "Physical unit declared",
            "description": "Checks whether the CAD parser resolved a physical unit system.",
            "evaluator": "unit_known",
            "operator": "eq",
            "limit_value": 1.0,
            "unit": "boolean",
            "severity": "high",
            "risk_type": "data_quality",
            "recommendation": (
                "Provide a source format with explicit units or map units at ingestion."
            ),
        },
        {
            "rule_id": "DEMO-PLANAR-MIN-011",
            "title": "Minimum analytic planar-face share",
            "description": (
                "Checks analytic STEP faces; tessellated STL triangles are not treated as planes."
            ),
            "evaluator": "surface_share",
            "parameters": {"surface_type": "plane"},
            "operator": "gte",
            "limit_value": 0.5,
            "unit": "ratio",
            "severity": "low",
            "risk_type": "surface_composition",
            "recommendation": "Review the analytic surface composition.",
        },
        {
            "rule_id": "DEMO-RIB-RATIO-012",
            "title": "Rib-to-wall thickness ratio",
            "description": (
                "Uses explicitly supplied Demo measurements; automated local CAD measurement "
                "is future scope."
            ),
            "evaluator": "context_ratio",
            "parameters": {
                "numerator": "max_rib_thickness_mm",
                "denominator": "nominal_wall_thickness_mm",
                "location": "context:rib-measurement",
            },
            "operator": "lte",
            "limit_value": 0.6,
            "unit": "ratio",
            "severity": "high",
            "risk_type": "sink_mark",
            "recommendation": "Reduce rib thickness or obtain a validated engineering waiver.",
        },
        {
            "rule_id": "DEMO-DRAFT-MIN-013",
            "title": "Minimum draft angle",
            "description": (
                "Uses an explicitly supplied Demo minimum angle; automatic face analysis "
                "is future scope."
            ),
            "evaluator": "context_value",
            "parameters": {
                "field": "minimum_draft_angle_deg",
                "location": "context:draft-angle-measurement",
            },
            "operator": "gte",
            "limit_value": 1.0,
            "unit": "deg",
            "severity": "medium",
            "risk_type": "ejection",
            "recommendation": "Increase draft or obtain a validated engineering waiver.",
        },
    ]


def _ruleset_checksum(specs: list[dict[str, object]]) -> str:
    return hashlib.sha256(
        json.dumps(specs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def get_demo_rule_profile() -> RuleProfile:
    specs = _rule_specs()
    checksum = _ruleset_checksum(specs)
    with transaction.atomic():
        profile = (
            RuleProfile.objects.filter(
                profile_key=PROFILE_KEY,
                workflow_status=RuleProfile.WorkflowStatus.PUBLISHED,
            )
            .order_by("-published_at", "-created_at")
            .first()
        )
        scope = DataScope.objects.filter(code="public-demo", is_active=True).first()
        if profile is None:
            profile = RuleProfile.objects.create(
                profile_key=PROFILE_KEY,
                version="1.0",
                status="approved_demo",
                product_scope=["public-demo"],
                material_scope=["synthetic"],
                owner="demo-rule-owner",
                approved_by="demo-technical-review",
                ruleset_checksum=checksum,
                workflow_status=RuleProfile.WorkflowStatus.PUBLISHED,
                scope=scope,
                classification="public_demo",
                is_default=True,
                priority=0,
            )
        if profile.ruleset_checksum != checksum:
            raise DesignReviewValidationError(
                "RULE_PROFILE_CHECKSUM_MISMATCH",
                "The seeded Demo profile differs from the version stored in the database.",
            )
        for order, spec in enumerate(specs, start=1):
            RuleVersion.objects.get_or_create(
                profile=profile,
                rule_id=str(spec["rule_id"]),
                rule_version="1.0",
                defaults={
                    **spec,
                    "applicability": {"formats": ["step", "stp", "stl"]},
                    "tolerance": 0.0,
                    "reference": {
                        "document": "Mold AI Demo Rule Catalog",
                        "revision": "1.0",
                        "classification": "synthetic_demo_not_engineering_guidance",
                    },
                    "sort_order": order,
                },
            )
        resolution_updates: list[str] = []
        if not profile.is_default:
            profile.is_default = True
            resolution_updates.append("is_default")
        if profile.scope_id is None and scope is not None:
            profile.scope = scope
            resolution_updates.append("scope")
        checksum_value = applicability_checksum(profile)
        if profile.applicability_checksum != checksum_value:
            profile.applicability_checksum = checksum_value
            resolution_updates.append("applicability_checksum")
        if resolution_updates:
            profile.save(update_fields=resolution_updates)
    return profile


def _normalized_context(context: object) -> dict[str, float]:
    if context is None:
        return {}
    if not isinstance(context, dict):
        raise DesignReviewValidationError("VALIDATION_REVIEW_CONTEXT", "context must be an object.")
    unknown = set(context) - ALLOWED_CONTEXT_KEYS
    if unknown:
        raise DesignReviewValidationError(
            "VALIDATION_REVIEW_CONTEXT",
            f"Unsupported context fields: {', '.join(sorted(unknown))}.",
        )
    normalized: dict[str, float] = {}
    for key, value in context.items():
        if value in (None, ""):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise DesignReviewValidationError(
                "VALIDATION_REVIEW_CONTEXT", f"{key} must be numeric."
            ) from exc
        if not math.isfinite(number) or number < 0:
            raise DesignReviewValidationError(
                "VALIDATION_REVIEW_CONTEXT", f"{key} must be a finite non-negative number."
            )
        normalized[key] = number
    return normalized


def create_design_review_records(
    artifact_version: ArtifactVersion,
    *,
    context: object = None,
    resolution_context: dict[str, object] | None = None,
    requested_profile_id: str | None = None,
    override_reason: str = "",
    idempotency_key: str | None = None,
    pinned_resolution: MoldPlanResolution | None = None,
    requested_by: str = "system",
) -> DesignReviewRecords:
    try:
        cad_model = CADModel.objects.select_related("artifact_version__artifact").get(
            artifact_version=artifact_version
        )
    except CADModel.DoesNotExist as exc:
        raise DesignReviewValidationError(
            "DESIGN_REVIEW_GEOMETRY_NOT_READY", "The selected artifact has no parsed CAD geometry."
        ) from exc
    if cad_model.geometry_status != CADModel.GeometryStatus.SUCCEEDED:
        raise DesignReviewValidationError(
            "DESIGN_REVIEW_GEOMETRY_NOT_READY", "CAD geometry must finish before design review."
        )

    normalized_key = idempotency_key.strip() if idempotency_key else None
    if normalized_key:
        existing_job = Job.objects.filter(idempotency_key=normalized_key).first()
        if existing_job:
            if existing_job.capability_id != CAPABILITY_ID:
                raise DesignReviewValidationError(
                    "CONFLICT_IDEMPOTENCY_KEY",
                    "The idempotency key is already used by another capability.",
                )
            return DesignReviewRecords(existing_job.design_review, existing_job, created=False)

    if pinned_resolution is None:
        get_demo_rule_profile()
    normalized = _normalized_context(context)
    if pinned_resolution is not None:
        plan = pinned_resolution.plan
        if plan.cad_artifact_version_id != artifact_version.id:
            raise DesignReviewValidationError(
                "MOLD_PLAN_CAD_MISMATCH",
                "The mold plan resolution does not reference this CAD version.",
            )
        profile = pinned_resolution.selected_profile
        if profile.ruleset_checksum != pinned_resolution.ruleset_checksum:
            raise DesignReviewValidationError(
                "MOLD_PLAN_RULESET_MISMATCH",
                "The saved mold plan ruleset no longer matches the selected rule profile.",
            )
        selected = next(
            (
                item
                for item in pinned_resolution.candidate_snapshot
                if str(item.get("profile_id")) == str(profile.id)
            ),
            {
                "profile_id": str(profile.id),
                "profile_key": profile.profile_key,
                "version": profile.version,
            },
        )
        resolution_snapshot = {
            "schema_version": "1.0",
            "resolved_at": pinned_resolution.resolved_at.isoformat(),
            "selection_mode": pinned_resolution.selection_mode,
            "context": pinned_resolution.context_snapshot,
            "candidates": pinned_resolution.candidate_snapshot,
            "selected": selected,
            "reason": pinned_resolution.reason,
            "override_reason": pinned_resolution.override_reason or None,
            "applicability_checksum": pinned_resolution.applicability_checksum,
            "mold_plan_id": str(plan.id),
            "mold_plan_resolution_id": str(pinned_resolution.id),
            "mold_plan_resolution_number": pinned_resolution.resolution_number,
        }
    else:
        try:
            resolution = resolve_rule_profile(
                artifact_version,
                extra_context=resolution_context,
                requested_profile_id=requested_profile_id,
                override_reason=override_reason,
            )
        except RuleResolutionError as exc:
            raise DesignReviewValidationError(exc.code, exc.user_message) from exc
        profile = resolution.profile
        resolution_snapshot = resolution.snapshot
    rules = list(profile.rules.filter(enabled=True))
    snapshot = {
        "schema_version": "1.0",
        "requested_by": (requested_by.strip() or "system")[:128],
        "cad_artifact_version_id": str(artifact_version.id),
        "cad_sha256": artifact_version.sha256,
        "cad_parser": f"{cad_model.parser_name}@{cad_model.parser_version}",
        "profile": profile.profile_key,
        "ruleset_checksum": profile.ruleset_checksum,
        "rules": [{"rule_id": rule.rule_id, "rule_version": rule.rule_version} for rule in rules],
        "context": normalized,
        "resolution": resolution_snapshot,
    }
    with transaction.atomic():
        job = Job.objects.create(
            capability_id=CAPABILITY_ID,
            capability_version=CAPABILITY_VERSION,
            state=Job.State.QUEUED,
            queue="cad",
            resource_class="cad",
            input_artifact_version=artifact_version,
            input_snapshot=snapshot,
            idempotency_key=normalized_key,
        )
        JobEvent.objects.create(
            job=job,
            from_state="",
            to_state=Job.State.QUEUED,
            stage="queued",
            progress=0,
        )
        review = ReviewRun.objects.create(
            job=job,
            cad_model=cad_model,
            profile=profile,
            context=normalized,
            input_snapshot=snapshot,
            resolution_snapshot=resolution_snapshot,
            geometry_engine_version=f"{cad_model.parser_name}@{cad_model.parser_version}",
        )
    return DesignReviewRecords(review, job, created=True)


def _comparison(rule: RuleVersion, actual: float) -> bool:
    if rule.limit_value is None:
        raise ValueError("A comparison rule requires a limit.")
    if rule.operator == "lte":
        return actual <= rule.limit_value + rule.tolerance
    if rule.operator == "gte":
        return actual >= rule.limit_value - rule.tolerance
    if rule.operator == "eq":
        return abs(actual - rule.limit_value) <= rule.tolerance
    raise ValueError(f"Unsupported operator: {rule.operator}")


def _measured(
    rule: RuleVersion, actual: float, location: str, *, flags: list[str] | None = None
) -> Evaluation:
    passed = _comparison(rule, actual)
    relation = {"lte": "≤", "gte": "≥", "eq": "="}[rule.operator]
    return Evaluation(
        result=ReviewFinding.Result.PASS if passed else ReviewFinding.Result.FAIL,
        actual_value=actual,
        message=(
            f"Measured {actual:g} {rule.unit}; required {relation} "
            f"{rule.limit_value:g} {rule.unit}."
        ),
        geometry_location={"scope": location},
        evidence_refs=[location],
        quality_flags=flags or [],
    )


def _not_evaluated(rule: RuleVersion, message: str, location: str) -> Evaluation:
    return Evaluation(
        result=ReviewFinding.Result.NOT_EVALUATED,
        actual_value=None,
        message=message,
        geometry_location={"scope": location},
        evidence_refs=[location],
        quality_flags=["MEASUREMENT_UNAVAILABLE"],
    )


def _bbox_dimension(rule: RuleVersion, cad: CADModel, context: dict[str, float]) -> Evaluation:
    if cad.unit_system != "mm":
        return _not_evaluated(
            rule,
            "Physical dimensions cannot be evaluated because units are not millimetres.",
            "model:bounding-box",
        )
    size = cad.bounding_box.get("size", {})
    values = [size.get(axis) for axis in ("x", "y", "z")]
    if any(value is None for value in values):
        return _not_evaluated(
            rule, "Bounding-box dimensions are unavailable.", "model:bounding-box"
        )
    aggregation = str(rule.parameters.get("aggregation"))
    actual = (max if aggregation == "max" else min)(float(value) for value in values)
    return _measured(rule, actual, "model:bounding-box")


def _bbox_aspect_ratio(rule: RuleVersion, cad: CADModel, context: dict[str, float]) -> Evaluation:
    size = cad.bounding_box.get("size", {})
    values = [float(size.get(axis, 0)) for axis in ("x", "y", "z")]
    smallest = min(values)
    if smallest <= 0:
        return _not_evaluated(rule, "A non-zero bounding box is required.", "model:bounding-box")
    return _measured(rule, max(values) / smallest, "model:bounding-box")


def _cad_scalar(rule: RuleVersion, cad: CADModel, context: dict[str, float]) -> Evaluation:
    field = str(rule.parameters.get("field"))
    location = str(rule.parameters.get("location", "model:geometry-summary"))
    if field in {"volume", "surface_area"} and cad.unit_system != "mm":
        return _not_evaluated(
            rule,
            "Physical measurement cannot be evaluated because source units are unknown.",
            location,
        )
    value = getattr(cad, field, None)
    if value is None:
        return _not_evaluated(rule, f"{field} is unavailable from the geometry parser.", location)
    return _measured(rule, float(value), location)


def _edge_face_ratio(rule: RuleVersion, cad: CADModel, context: dict[str, float]) -> Evaluation:
    if cad.face_count in (None, 0) or cad.edge_count is None:
        return _not_evaluated(rule, "Topology counts are unavailable.", "model:topology-summary")
    return _measured(rule, cad.edge_count / cad.face_count, "model:topology-summary")


def _quality_flag_absent(rule: RuleVersion, cad: CADModel, context: dict[str, float]) -> Evaluation:
    flag = str(rule.parameters.get("flag"))
    actual = 1.0 if flag in cad.quality_flags else 0.0
    return _measured(rule, actual, "model:quality-flags")


def _unit_known(rule: RuleVersion, cad: CADModel, context: dict[str, float]) -> Evaluation:
    actual = 0.0 if cad.unit_system in {"", "unknown"} else 1.0
    return _measured(rule, actual, "artifact:unit-system")


def _surface_share(rule: RuleVersion, cad: CADModel, context: dict[str, float]) -> Evaluation:
    surface_type = str(rule.parameters.get("surface_type"))
    if cad.cad_format == "stl" or surface_type not in cad.surface_type_histogram:
        return _not_evaluated(
            rule,
            "Analytic surface classification is unavailable for this representation.",
            "model:surface-types",
        )
    if not cad.face_count:
        return _not_evaluated(rule, "Face count is unavailable.", "model:surface-types")
    actual = float(cad.surface_type_histogram[surface_type]) / cad.face_count
    return _measured(rule, actual, "model:surface-types")


def _context_ratio(rule: RuleVersion, cad: CADModel, context: dict[str, float]) -> Evaluation:
    numerator_key = str(rule.parameters.get("numerator"))
    denominator_key = str(rule.parameters.get("denominator"))
    location = str(rule.parameters.get("location"))
    if numerator_key not in context or denominator_key not in context:
        return _not_evaluated(
            rule, "Validated local rib and wall measurements were not supplied.", location
        )
    denominator = context[denominator_key]
    if denominator <= 0:
        return _not_evaluated(rule, "Nominal wall thickness must be greater than zero.", location)
    return _measured(
        rule,
        context[numerator_key] / denominator,
        location,
        flags=["USER_SUPPLIED_DEMO_MEASUREMENT"],
    )


def _context_value(rule: RuleVersion, cad: CADModel, context: dict[str, float]) -> Evaluation:
    field = str(rule.parameters.get("field"))
    location = str(rule.parameters.get("location"))
    if field not in context:
        return _not_evaluated(
            rule, "A validated local draft-angle measurement was not supplied.", location
        )
    return _measured(rule, context[field], location, flags=["USER_SUPPLIED_DEMO_MEASUREMENT"])


Evaluator = Callable[[RuleVersion, CADModel, dict[str, float]], Evaluation]
EVALUATORS: dict[str, Evaluator] = {
    "bbox_dimension": _bbox_dimension,
    "bbox_aspect_ratio": _bbox_aspect_ratio,
    "cad_scalar": _cad_scalar,
    "edge_face_ratio": _edge_face_ratio,
    "quality_flag_absent": _quality_flag_absent,
    "unit_known": _unit_known,
    "surface_share": _surface_share,
    "context_ratio": _context_ratio,
    "context_value": _context_value,
}


def evaluate_review(review: ReviewRun) -> dict[str, object]:
    rules = list(review.profile.rules.filter(enabled=True))
    findings: list[ReviewFinding] = []
    for rule in rules:
        formats = rule.applicability.get("formats", [])
        if formats and review.cad_model.cad_format not in formats:
            evaluation = Evaluation(
                ReviewFinding.Result.NOT_APPLICABLE,
                None,
                "The rule does not apply to this CAD format.",
                {"scope": "artifact:format"},
                ["artifact:format"],
                [],
            )
        else:
            evaluator = EVALUATORS.get(rule.evaluator)
            if evaluator is None:
                evaluation = Evaluation(
                    ReviewFinding.Result.ERROR,
                    None,
                    "The registered evaluator is unavailable.",
                    {"scope": "rule:evaluator"},
                    [f"rule:{rule.rule_id}@{rule.rule_version}"],
                    ["EVALUATOR_UNAVAILABLE"],
                )
            else:
                try:
                    evaluation = evaluator(rule, review.cad_model, review.context)
                except Exception:
                    evaluation = Evaluation(
                        ReviewFinding.Result.ERROR,
                        None,
                        "The deterministic evaluator failed. Use the review ID for support.",
                        {"scope": "rule:evaluator"},
                        [f"rule:{rule.rule_id}@{rule.rule_version}"],
                        ["EVALUATION_ERROR"],
                    )
        findings.append(
            ReviewFinding(
                review_run=review,
                rule_version=rule,
                result=evaluation.result,
                actual_value=evaluation.actual_value,
                limit_value=rule.limit_value,
                unit=rule.unit,
                severity=rule.severity,
                risk_type=rule.risk_type,
                geometry_location=evaluation.geometry_location,
                evidence_refs=evaluation.evidence_refs,
                quality_flags=evaluation.quality_flags,
                message=evaluation.message,
            )
        )
    with transaction.atomic():
        ReviewFinding.objects.bulk_create(findings)
        counts = {choice: 0 for choice, _ in ReviewFinding.Result.choices}
        for finding in findings:
            counts[finding.result] += 1
        summary = {
            "total": len(findings),
            "counts": counts,
            "decision": "FAIL"
            if counts[ReviewFinding.Result.FAIL]
            else (
                "INCOMPLETE"
                if counts[ReviewFinding.Result.NOT_EVALUATED] or counts[ReviewFinding.Result.ERROR]
                else "PASS"
            ),
        }
        review.review_status = ReviewRun.Status.SUCCEEDED
        review.result_summary = summary
        review.completed_at = timezone.now()
        review.save(update_fields=["review_status", "result_summary", "completed_at"])
    return summary


def create_review_decision(
    finding: ReviewFinding,
    *,
    decision: str,
    reason: str,
    decided_by: str,
    approved_by: str,
) -> ReviewDecision:
    valid = {choice for choice, _ in ReviewDecision.Decision.choices}
    if finding.result != ReviewFinding.Result.FAIL:
        raise DesignReviewValidationError(
            "DECISION_FINDING_NOT_FAILED", "Decisions can only be recorded for failed findings."
        )
    if decision not in valid:
        raise DesignReviewValidationError(
            "VALIDATION_REVIEW_DECISION", "decision must be accepted, rejected, or waived."
        )
    reason = reason.strip()
    decided_by = decided_by.strip()
    approved_by = approved_by.strip()
    if not decided_by:
        raise DesignReviewValidationError("VALIDATION_DECIDED_BY", "decided_by is required.")
    if (
        decision in {ReviewDecision.Decision.REJECTED, ReviewDecision.Decision.WAIVED}
        and not reason
    ):
        raise DesignReviewValidationError(
            "VALIDATION_DECISION_REASON", "A reason is required for rejected or waived findings."
        )
    if decision == ReviewDecision.Decision.WAIVED and not approved_by:
        raise DesignReviewValidationError(
            "VALIDATION_WAIVER_APPROVER", "approved_by is required for a waiver."
        )
    audit_detail = {
        "finding_id": str(finding.id),
        "review_id": str(finding.review_run_id),
        "decision": decision,
        "reason": reason,
        "approved_by": approved_by,
        "finding_result_unchanged": finding.result,
    }
    payload_hash = hashlib.sha256(
        json.dumps(audit_detail, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with transaction.atomic():
        record = ReviewDecision.objects.create(
            finding=finding,
            decision=decision,
            reason=reason,
            decided_by=decided_by,
            approved_by=approved_by,
        )
        AuditEvent.objects.create(
            event_type="design_review.finding_decided",
            actor_id=decided_by,
            target_refs=[f"review:{finding.review_run_id}", f"finding:{finding.id}"],
            detail={**audit_detail, "decision_id": str(record.id)},
            payload_hash=payload_hash,
        )
    return record
