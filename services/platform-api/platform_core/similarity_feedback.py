import math
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .identity import audit_identity_event
from .models import (
    ArtifactVersion,
    CADCrossModalProfile,
    FeatureSet,
    SimilarityFeedback,
    SimilaritySearch,
)

NEGATIVE_REASON_CODES = {
    "different_function",
    "different_manufacturing_process",
    "geometry_not_comparable",
    "wrong_scale",
    "other_engineering_reason",
}


class SimilarityFeedbackValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


@dataclass(frozen=True)
class FeedbackResult:
    feedback: SimilarityFeedback
    created: bool


def engineering_profile_payload(profile: CADCrossModalProfile) -> dict[str, object]:
    return {
        "artifact_version_id": str(profile.artifact_version_id),
        "tolerance_strictness": profile.tolerance_strictness,
        "ctq_count": profile.ctq_count,
        "surface_roughness_ra": profile.surface_roughness_ra,
        "flow_length_ratio": profile.flow_length_ratio,
        "projected_area": profile.projected_area,
        "clamp_force_band": profile.clamp_force_band or None,
        "gate_type": profile.gate_type or None,
        "source_mode": profile.source_mode,
        "row_version": profile.row_version,
        "updated_by": profile.updated_by,
        "updated_at": profile.updated_at.isoformat(),
    }


def _positive_float(value: object, field: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SimilarityFeedbackValidationError(
            "VALIDATION_ENGINEERING_PROFILE", f"{field} must be numeric."
        ) from exc
    if not math.isfinite(number) or number <= 0:
        raise SimilarityFeedbackValidationError(
            "VALIDATION_ENGINEERING_PROFILE", f"{field} must be greater than zero."
        )
    return number


def save_engineering_profile(
    version: ArtifactVersion, payload: dict[str, object], *, actor_id: str
) -> tuple[CADCrossModalProfile, bool]:
    tolerance = str(payload.get("tolerance_strictness", "standard"))
    if tolerance not in CADCrossModalProfile.ToleranceStrictness.values:
        raise SimilarityFeedbackValidationError(
            "VALIDATION_ENGINEERING_PROFILE", "tolerance_strictness is invalid."
        )
    try:
        ctq_count = int(payload.get("ctq_count", 0))
    except (TypeError, ValueError) as exc:
        raise SimilarityFeedbackValidationError(
            "VALIDATION_ENGINEERING_PROFILE", "ctq_count must be an integer."
        ) from exc
    if not 0 <= ctq_count <= 10000:
        raise SimilarityFeedbackValidationError(
            "VALIDATION_ENGINEERING_PROFILE", "ctq_count must be between 0 and 10000."
        )
    values = {
        "tolerance_strictness": tolerance,
        "ctq_count": ctq_count,
        "surface_roughness_ra": _positive_float(
            payload.get("surface_roughness_ra"), "surface_roughness_ra"
        ),
        "flow_length_ratio": _positive_float(payload.get("flow_length_ratio"), "flow_length_ratio"),
        "projected_area": _positive_float(payload.get("projected_area"), "projected_area"),
        "clamp_force_band": str(payload.get("clamp_force_band", "")).strip()[:64],
        "gate_type": str(payload.get("gate_type", "")).strip()[:64],
        "updated_by": actor_id[:128],
    }
    existing = CADCrossModalProfile.objects.filter(artifact_version=version).first()
    if existing:
        supplied_row = payload.get("row_version")
        try:
            expected_row = int(supplied_row) if supplied_row is not None else None
        except (TypeError, ValueError):
            expected_row = None
        if expected_row != existing.row_version:
            raise SimilarityFeedbackValidationError(
                "CONFLICT_ROW_VERSION", "Engineering profile changed; refresh before saving."
            )
        before = engineering_profile_payload(existing)
        for field, value in values.items():
            setattr(existing, field, value)
        existing.row_version += 1
        existing.save()
        profile, created = existing, False
    else:
        before = None
        profile = CADCrossModalProfile.objects.create(artifact_version=version, **values)
        created = True
    audit_identity_event(
        "similarity.engineering_profile.saved.v1",
        actor_id=actor_id,
        target_refs=[f"artifact-version:{version.id}"],
        detail={"before": before, "after": engineering_profile_payload(profile)},
    )
    return profile, created


def _ratio(first: float | int | None, second: float | int | None) -> float | None:
    if first is None or second is None:
        return None
    if float(first) == 0 and float(second) == 0:
        return 1.0
    if float(first) <= 0 or float(second) <= 0:
        return 0.0
    return math.exp(-abs(math.log(float(first) / float(second))))


def compare_cross_modal(
    query_version: ArtifactVersion, candidate_version: ArtifactVersion
) -> dict[str, object]:
    try:
        query = query_version.similarity_engineering_profile
        candidate = candidate_version.similarity_engineering_profile
    except CADCrossModalProfile.DoesNotExist:
        return {
            "tolerance": None,
            "cae": None,
            "availability": {"tolerance": False, "cae": False},
            "evidence": [],
        }
    tolerance_parts = [
        1.0 if query.tolerance_strictness == candidate.tolerance_strictness else 0.35,
        _ratio(query.ctq_count, candidate.ctq_count),
        _ratio(query.surface_roughness_ra, candidate.surface_roughness_ra),
    ]
    tolerance_values = [value for value in tolerance_parts if value is not None]
    tolerance_score = sum(tolerance_values) / len(tolerance_values)
    cae_parts = [
        _ratio(query.flow_length_ratio, candidate.flow_length_ratio),
        _ratio(query.projected_area, candidate.projected_area),
    ]
    if query.clamp_force_band and candidate.clamp_force_band:
        cae_parts.append(1.0 if query.clamp_force_band == candidate.clamp_force_band else 0.0)
    if query.gate_type and candidate.gate_type:
        cae_parts.append(1.0 if query.gate_type == candidate.gate_type else 0.0)
    cae_values = [value for value in cae_parts if value is not None]
    cae_score = sum(cae_values) / len(cae_values) if cae_values else None
    return {
        "tolerance": round(tolerance_score, 6),
        "cae": round(cae_score, 6) if cae_score is not None else None,
        "availability": {"tolerance": True, "cae": cae_score is not None},
        "evidence": [
            {
                "type": "manual_ctq_profile",
                "message": (
                    "Tolerance and CTQ strictness were compared from governed manual profiles."
                ),
                "evidence_ref": f"engineering-profile:{candidate.id}",
            }
        ],
    }


def matches_engineering_filters(version: ArtifactVersion, filters: dict[str, list[str]]) -> bool:
    requested = {
        "tolerance_strictness": filters.get("tolerance_strictness", []),
        "clamp_force_band": filters.get("clamp_force_bands", []),
        "gate_type": filters.get("gate_types", []),
    }
    active = {field: values for field, values in requested.items() if values}
    if not active:
        return True
    try:
        profile = version.similarity_engineering_profile
    except CADCrossModalProfile.DoesNotExist:
        return False
    return all(str(getattr(profile, field)) in values for field, values in active.items())


def fuse_cross_modal(base: dict[str, object], cross_modal: dict[str, object]) -> dict[str, object]:
    available = [lane for lane in ("tolerance", "cae") if cross_modal["availability"].get(lane)]
    if not available:
        return base
    lane_weight = 0.075
    cross_weight = lane_weight * len(available)
    base["overall_score"] = round(
        float(base["overall_score"]) * (1.0 - cross_weight)
        + sum(float(cross_modal[lane]) * lane_weight for lane in available),
        6,
    )
    base["effective_weights"] = {
        lane: round(float(weight) * (1.0 - cross_weight), 6)
        for lane, weight in base["effective_weights"].items()
    }
    base["effective_weights"].update({lane: lane_weight for lane in available})
    base["sub_scores"].update(
        {lane: cross_modal[lane] if lane in available else None for lane in ("tolerance", "cae")}
    )
    base["feature_availability"].update(cross_modal["availability"])
    base["similarities"].extend(cross_modal["evidence"])
    base["fusion_contract"] = "manual-ctq-cae@1.0"
    return base


def create_feedback(
    search: SimilaritySearch,
    candidate: FeatureSet,
    *,
    action: str,
    reason_code: str,
    actor_id: str,
    scope_id: str,
    idempotency_key: str,
) -> FeedbackResult:
    if action not in SimilarityFeedback.Action.values:
        raise SimilarityFeedbackValidationError("VALIDATION_FEEDBACK_ACTION", "action is invalid.")
    reason = reason_code.strip()
    if action == SimilarityFeedback.Action.NOT_RELEVANT and reason not in NEGATIVE_REASON_CODES:
        raise SimilarityFeedbackValidationError(
            "VALIDATION_FEEDBACK_REASON", "An approved engineering reason is required."
        )
    existing = SimilarityFeedback.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if existing.search_id != search.id or existing.candidate_feature_set_id != candidate.id:
            raise SimilarityFeedbackValidationError(
                "CONFLICT_IDEMPOTENCY_KEY", "The idempotency key belongs to another feedback event."
            )
        return FeedbackResult(existing, False)
    with transaction.atomic():
        feedback = SimilarityFeedback.objects.create(
            search=search,
            candidate_feature_set=candidate,
            action=action,
            reason_code=reason if action == SimilarityFeedback.Action.NOT_RELEVANT else "",
            actor_id=actor_id[:128],
            scope_id=scope_id[:128],
            idempotency_key=idempotency_key[:255],
            expires_at=timezone.now()
            + timedelta(days=int(settings.SIMILARITY_FEEDBACK_RETENTION_DAYS)),
        )
        audit_identity_event(
            "similarity.feedback.recorded.v1",
            actor_id=actor_id,
            target_refs=[
                f"similarity-search:{search.id}",
                f"feature-set:{candidate.id}",
                f"similarity-feedback:{feedback.id}",
            ],
            detail={"action": action, "reason_code": feedback.reason_code, "scope_id": scope_id},
        )
    return FeedbackResult(feedback, True)
