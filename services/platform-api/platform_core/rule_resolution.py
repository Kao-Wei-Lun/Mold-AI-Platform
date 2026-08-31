from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db.models import Q

from .models import ArtifactVersion, DataScope, MasterDataItem, MoldRevision, RuleProfile


class RuleResolutionError(Exception):
    def __init__(self, code: str, message: str, *, candidates: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.code = code
        self.user_message = message
        self.candidates = candidates or []


@dataclass(frozen=True)
class RuleResolution:
    profile: RuleProfile
    snapshot: dict[str, Any]


def applicability_checksum(profile: RuleProfile) -> str:
    entries = [
        {
            "dimension": entry.dimension,
            "value_code": entry.value_code,
            "match_mode": entry.match_mode,
        }
        for entry in profile.applicability_entries.all()
    ]
    content = {
        "profile_id": str(profile.id),
        "entries": sorted(
            entries,
            key=lambda item: (item["dimension"], item["match_mode"], item["value_code"]),
        ),
        "priority": profile.priority,
        "is_default": profile.is_default,
        "effective_from": profile.effective_from.isoformat() if profile.effective_from else None,
        "effective_to": profile.effective_to.isoformat() if profile.effective_to else None,
        "scope": profile.scope.code if profile.scope_id else None,
        "classification": profile.classification,
        "resolution_status": profile.resolution_status,
    }
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def context_for_artifact(
    artifact_version: ArtifactVersion, extra_context: dict[str, object] | None = None
) -> dict[str, str]:
    unknown = set(extra_context or {}) - {"molding_process", "location"}
    if unknown:
        raise RuleResolutionError(
            "VALIDATION_RESOLUTION_CONTEXT",
            f"Unsupported resolution context fields: {', '.join(sorted(unknown))}.",
        )
    artifact = artifact_version.artifact
    context: dict[str, str] = {
        "product_type": artifact.product_type,
        "material": artifact.material_code,
    }
    if artifact.mold_revision_id:
        mold = artifact.mold_revision.mold
        context.update(
            {
                "mold_type": mold.mold_type,
                "project": mold.project.code,
            }
        )
        item = MasterDataItem.objects.filter(
            scope=mold.project.scope,
            kind=MasterDataItem.Kind.MOLD_TYPE,
            code=mold.mold_type,
            status=MasterDataItem.Status.ACTIVE,
        ).first()
        process_family = (item.attributes if item else {}).get("process_family")
        if process_family:
            context["molding_process"] = str(process_family)
    for key in ("molding_process", "location"):
        value = str((extra_context or {}).get(key, "")).strip()
        if value:
            context[key] = value
    return {key: value for key, value in context.items() if value}


def _candidate_payload(
    profile: RuleProfile, *, specificity: int, matched_dimensions: list[str]
) -> dict[str, Any]:
    return {
        "profile_id": str(profile.id),
        "profile_key": profile.profile_key,
        "display_name": profile.profile_key.replace("-", " ").replace("_", " ").title(),
        "version": profile.version,
        "workflow_status": profile.workflow_status,
        "owner": profile.owner,
        "approved_by": profile.approved_by,
        "effective_from": profile.effective_from.isoformat() if profile.effective_from else None,
        "effective_to": profile.effective_to.isoformat() if profile.effective_to else None,
        "specificity": specificity,
        "priority": profile.priority,
        "is_default": profile.is_default,
        "matched_dimensions": matched_dimensions,
        "applicability_checksum": profile.applicability_checksum or applicability_checksum(profile),
    }


def resolve_rule_profile_for_context(
    context: dict[str, str],
    *,
    scope: DataScope | None,
    classification: str,
    requested_profile_id: str | None = None,
    override_reason: str = "",
    today: date | None = None,
) -> RuleResolution:
    current_date = today or date.today()
    profiles = (
        RuleProfile.objects.prefetch_related("applicability_entries")
        .select_related("scope")
        .filter(
            workflow_status=RuleProfile.WorkflowStatus.PUBLISHED,
            resolution_status=RuleProfile.ResolutionStatus.ELIGIBLE,
        )
        .filter(Q(effective_from__isnull=True) | Q(effective_from__lte=current_date))
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=current_date))
        .filter(Q(scope__isnull=True) | Q(scope=scope))
        .filter(classification=classification)
    )
    eligible: list[tuple[RuleProfile, int, list[str]]] = []
    excluded_summary: list[dict[str, Any]] = []
    for profile in profiles:
        includes: dict[str, set[str]] = {}
        excluded_dimensions: list[str] = []
        for entry in profile.applicability_entries.all():
            if entry.match_mode == entry.MatchMode.EXCLUDE:
                if context.get(entry.dimension) == entry.value_code:
                    excluded_dimensions.append(entry.dimension)
            else:
                includes.setdefault(entry.dimension, set()).add(entry.value_code)
        mismatched = sorted(
            key for key, values in includes.items() if context.get(key) not in values
        )
        if excluded_dimensions or mismatched:
            excluded_summary.append(
                {
                    "profile_id": str(profile.id),
                    "profile_key": profile.profile_key,
                    "reason_code": "EXCLUDED_VALUE" if excluded_dimensions else "INCLUDE_MISMATCH",
                    "dimensions": sorted(set(excluded_dimensions or mismatched)),
                }
            )
            continue
        matched = sorted(includes)
        eligible.append((profile, len(matched), matched))

    candidates = [
        _candidate_payload(profile, specificity=specificity, matched_dimensions=matched)
        for profile, specificity, matched in eligible
    ]
    if requested_profile_id:
        selected = next(
            (item for item in eligible if str(item[0].id) == str(requested_profile_id)), None
        )
        if selected is None:
            raise RuleResolutionError(
                "RULE_PROFILE_OVERRIDE_NOT_ELIGIBLE",
                "The requested rule profile is not published, effective, visible, or applicable.",
                candidates=candidates,
            )
        if not override_reason.strip():
            raise RuleResolutionError(
                "VALIDATION_OVERRIDE_REASON",
                "A reason is required when overriding automatic rule profile resolution.",
                candidates=candidates,
            )
        profile, specificity, matched = selected
        selection_mode = "manual_override"
        reason = f"Manually selected with reason: {override_reason.strip()}"
    else:
        non_defaults = [item for item in eligible if not item[0].is_default]
        ranked = non_defaults or [item for item in eligible if item[0].is_default]
        ranked.sort(key=lambda item: (item[1], item[0].priority), reverse=True)
        if not ranked:
            raise RuleResolutionError(
                "RULE_PROFILE_NOT_FOUND",
                "No published and effective rule profile matches this engineering context.",
                candidates=candidates,
            )
        best_score = (ranked[0][1], ranked[0][0].priority)
        tied = [item for item in ranked if (item[1], item[0].priority) == best_score]
        if len(tied) > 1:
            raise RuleResolutionError(
                "RULE_PROFILE_AMBIGUOUS",
                "Multiple rule profiles have the same specificity and priority; review is blocked.",
                candidates=candidates,
            )
        profile, specificity, matched = ranked[0]
        selection_mode = "default" if profile.is_default else "automatic"
        reason = (
            "Selected the default published profile because no more specific profile matched."
            if profile.is_default
            else (
                "Selected the most specific published profile "
                f"({specificity} matched dimensions), then highest priority "
                f"({profile.priority})."
            )
        )

    checksum = profile.applicability_checksum or applicability_checksum(profile)
    if profile.applicability_checksum != checksum:
        RuleProfile.objects.filter(pk=profile.pk).update(applicability_checksum=checksum)
        profile.applicability_checksum = checksum
    return RuleResolution(
        profile=profile,
        snapshot={
            "schema_version": "1.0",
            "resolved_at": date.today().isoformat(),
            "selection_mode": selection_mode,
            "context": context,
            "candidates": candidates,
            "excluded_summary": excluded_summary,
            "selected": _candidate_payload(
                profile, specificity=specificity, matched_dimensions=matched
            ),
            "reason": reason,
            "override_reason": override_reason.strip() or None,
            "applicability_checksum": checksum,
        },
    )


def planning_context_for_revision(
    revision: MoldRevision,
    *,
    artifact_version: ArtifactVersion | None = None,
    extra_context: dict[str, object] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    allowed = {"product_type", "material", "molding_process", "location"}
    unknown = set(extra_context or {}) - allowed
    if unknown:
        raise RuleResolutionError(
            "VALIDATION_RESOLUTION_CONTEXT",
            f"Unsupported resolution context fields: {', '.join(sorted(unknown))}.",
        )
    mold = revision.mold
    context: dict[str, str] = {"mold_type": mold.mold_type, "project": mold.project.code}
    sources: dict[str, dict[str, str]] = {
        "mold_type": {"source_type": "registry", "source_ref": str(mold.id)},
        "project": {"source_type": "registry", "source_ref": str(mold.project_id)},
    }
    if mold.product_part_id:
        context.update(
            {
                "product_type": mold.product_part.product_type,
                "material": mold.product_part.material_code,
            }
        )
        sources.update(
            {
                "product_type": {
                    "source_type": "registry",
                    "source_ref": str(mold.product_part_id),
                },
                "material": {"source_type": "registry", "source_ref": str(mold.product_part_id)},
            }
        )
    if artifact_version:
        artifact = artifact_version.artifact
        for dimension, value in (
            ("product_type", artifact.product_type),
            ("material", artifact.material_code),
        ):
            if value:
                context[dimension] = value
                sources[dimension] = {"source_type": "cad", "source_ref": str(artifact_version.id)}
    item = MasterDataItem.objects.filter(
        scope=mold.project.scope,
        kind=MasterDataItem.Kind.MOLD_TYPE,
        code=mold.mold_type,
        status=MasterDataItem.Status.ACTIVE,
    ).first()
    if process_family := (item.attributes if item else {}).get("process_family"):
        context["molding_process"] = str(process_family)
        sources["molding_process"] = {
            "source_type": "reference_data",
            "source_ref": str(item.id),
        }
    for key, raw_value in (extra_context or {}).items():
        value = str(raw_value or "").strip()
        if value:
            context[key] = value
            sources[key] = {"source_type": "user_confirmed", "source_ref": "planning_preview"}
    return {key: value for key, value in context.items() if value}, sources


def resolve_rule_profile(
    artifact_version: ArtifactVersion,
    *,
    extra_context: dict[str, object] | None = None,
    requested_profile_id: str | None = None,
    override_reason: str = "",
    today: date | None = None,
) -> RuleResolution:
    artifact_version = ArtifactVersion.objects.select_related(
        "artifact__mold_revision__mold__project__scope"
    ).get(pk=artifact_version.pk)
    artifact = artifact_version.artifact
    scope = (
        artifact.mold_revision.mold.project.scope
        if artifact.mold_revision_id
        else DataScope.objects.filter(code="public-demo", is_active=True).first()
    )
    context = context_for_artifact(artifact_version, extra_context)
    for dimension, kind in (
        ("molding_process", MasterDataItem.Kind.MOLDING_PROCESS),
        ("location", MasterDataItem.Kind.LOCATION),
    ):
        if (
            dimension in context
            and not MasterDataItem.objects.filter(
                scope=scope,
                kind=kind,
                code=context[dimension],
                status=MasterDataItem.Status.ACTIVE,
            ).exists()
        ):
            raise RuleResolutionError(
                "VALIDATION_RESOLUTION_CONTEXT",
                f"{dimension} must be an active governed engineering reference value.",
            )
    return resolve_rule_profile_for_context(
        context,
        scope=scope,
        classification=artifact.classification,
        requested_profile_id=requested_profile_id,
        override_reason=override_reason,
        today=today,
    )
