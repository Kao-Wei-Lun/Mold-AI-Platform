import hashlib
import json

from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, CAEComparison, CAEResult, CAERun, CAEStudy

COMPATIBILITY_PROFILE_VERSION = "cae-run-compatibility@1.0.0"
METRIC_CATALOG = {
    "fill_time_s": {"label": "Fill time", "direction": "lower_is_better"},
    "max_injection_pressure_mpa": {
        "label": "Maximum injection pressure",
        "direction": "lower_is_better",
    },
    "min_melt_front_temperature_c": {
        "label": "Minimum melt-front temperature",
        "direction": "target_controlled",
    },
    "weld_line_count": {"label": "Weld-line count", "direction": "lower_is_better"},
    "air_trap_count": {"label": "Air-trap count", "direction": "lower_is_better"},
    "max_warpage_mm": {"label": "Maximum warpage", "direction": "lower_is_better"},
}


class CAEValidationError(ValueError):
    def __init__(self, code: str, user_message: str) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


def _result_payload(result: CAEResult) -> dict[str, object]:
    return {
        "result_id": str(result.id),
        "metric_code": result.metric_code,
        "metric_label": METRIC_CATALOG.get(result.metric_code, {}).get(
            "label", result.metric_code.replace("_", " ")
        ),
        "result_type": result.result_type,
        "value": result.value,
        "unit": result.unit,
        "location": result.location,
        "field_summary": result.field_summary,
        "quality_flags": result.quality_flags,
        "parser": {"name": result.parser_name, "version": result.parser_version},
        "source_locator": result.source_locator,
        "evidence_refs": [
            f"cae-study:{result.run.study_id}",
            f"cae-run:{result.run_id}",
            f"cae-result:{result.id}",
            f"cae-metric:{result.metric_code}",
        ],
    }


def _run_payload(run: CAERun) -> dict[str, object]:
    return {
        "run_id": str(run.id),
        "run_code": run.run_code,
        "solver": {"name": run.solver_name, "version": run.solver_version},
        "mesh": {
            "artifact_ref": run.mesh_artifact_ref,
            "checksum": run.mesh_checksum,
            "family": run.study.mesh_family,
        },
        "material_model_code": run.material_model_code,
        "boundary_settings": run.boundary_settings,
        "process_settings": run.process_settings,
        "unit_system": run.unit_system,
        "status": run.status,
        "input_hash": run.input_hash,
        "data_quality": run.data_quality,
        "results": [_result_payload(result) for result in run.results.all()],
    }


def cae_study_payload(study: CAEStudy) -> dict[str, object]:
    return {
        "study_id": str(study.id),
        "study_code": study.study_code,
        "solver_name": study.solver_name,
        "product_ref": study.product_ref,
        "mold_revision_ref": study.mold_revision_ref,
        "material_model_code": study.material_model_code,
        "mesh_family": study.mesh_family,
        "objective": study.objective,
        "owner": study.owner,
        "classification": study.classification,
        "acl_scopes": study.acl_scopes,
        "data_quality": study.data_quality,
        "lifecycle_status": study.lifecycle_status,
        "row_version": study.row_version,
        "archive_reason": study.archive_reason or None,
        "archived_at": study.archived_at.isoformat() if study.archived_at else None,
        "provenance": {
            "connector_key": study.connector_key,
            "integration_level": study.integration_level,
            "source_record_id": study.source_record_id,
            "source_version": study.source_version,
            "source_hash": study.source_hash,
            "mapping_version": study.mapping_version,
            "official_solver_api_connected": False,
        },
        "runs": [_run_payload(run) for run in study.runs.all()],
    }


def cae_study_queryset():
    return CAEStudy.objects.filter(classification="public_demo").prefetch_related("runs__results")


def _incompatibility(field: str, baseline: object, candidate: object) -> dict[str, object]:
    return {
        "code": f"CAE_INCOMPATIBLE_{field.upper()}",
        "field": field,
        "baseline": baseline,
        "candidate": candidate,
    }


def evaluate_run_compatibility(baseline: CAERun, candidate: CAERun) -> list[dict[str, object]]:
    incompatibilities: list[dict[str, object]] = []

    def require_equal(field: str, baseline_value: object, candidate_value: object) -> None:
        if baseline_value != candidate_value:
            incompatibilities.append(_incompatibility(field, baseline_value, candidate_value))

    require_equal("solver_name", baseline.solver_name, candidate.solver_name)
    require_equal("solver_version", baseline.solver_version, candidate.solver_version)
    require_equal("material_model", baseline.material_model_code, candidate.material_model_code)
    require_equal("mesh_checksum", baseline.mesh_checksum, candidate.mesh_checksum)
    require_equal("mesh_family", baseline.study.mesh_family, candidate.study.mesh_family)
    require_equal(
        "mold_revision", baseline.study.mold_revision_ref, candidate.study.mold_revision_ref
    )
    require_equal("unit_system", baseline.unit_system, candidate.unit_system)
    require_equal("boundary_settings", baseline.boundary_settings, candidate.boundary_settings)
    if baseline.status != CAERun.Status.SUCCEEDED:
        incompatibilities.append(_incompatibility("baseline_status", "succeeded", baseline.status))
    if candidate.status != CAERun.Status.SUCCEEDED:
        incompatibilities.append(
            _incompatibility("candidate_status", "succeeded", candidate.status)
        )
    return incompatibilities


def _metric_state(metric_code: str, delta: float) -> str:
    if abs(delta) < 1e-12:
        return "unchanged"
    direction = METRIC_CATALOG.get(metric_code, {}).get("direction", "target_controlled")
    if direction == "lower_is_better":
        return "improved" if delta < 0 else "worsened"
    return "changed_review_required"


def _metric_comparisons(
    baseline: CAERun, candidate: CAERun
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    baseline_results = {result.metric_code: result for result in baseline.results.all()}
    candidate_results = {result.metric_code: result for result in candidate.results.all()}
    comparisons: list[dict[str, object]] = []
    metric_incompatibilities: list[dict[str, object]] = []
    for metric_code in sorted(set(baseline_results) | set(candidate_results)):
        baseline_result = baseline_results.get(metric_code)
        candidate_result = candidate_results.get(metric_code)
        if baseline_result is None or candidate_result is None:
            metric_incompatibilities.append(
                {
                    "code": "CAE_METRIC_MISSING",
                    "metric_code": metric_code,
                    "baseline_present": baseline_result is not None,
                    "candidate_present": candidate_result is not None,
                }
            )
            continue
        if (
            baseline_result.unit != candidate_result.unit
            or baseline_result.result_type != candidate_result.result_type
        ):
            metric_incompatibilities.append(
                {
                    "code": "CAE_METRIC_SCHEMA_MISMATCH",
                    "metric_code": metric_code,
                    "baseline": {
                        "unit": baseline_result.unit,
                        "result_type": baseline_result.result_type,
                    },
                    "candidate": {
                        "unit": candidate_result.unit,
                        "result_type": candidate_result.result_type,
                    },
                }
            )
            continue
        blocking_flags = set(baseline_result.quality_flags) | set(candidate_result.quality_flags)
        if blocking_flags:
            metric_incompatibilities.append(
                {
                    "code": "CAE_METRIC_QUALITY_BLOCKED",
                    "metric_code": metric_code,
                    "quality_flags": sorted(blocking_flags),
                }
            )
            continue
        delta = candidate_result.value - baseline_result.value
        percent_delta = None
        if baseline_result.value != 0:
            percent_delta = (delta / abs(baseline_result.value)) * 100
        evidence_refs = [
            f"cae-study:{baseline.study_id}",
            f"cae-run:{baseline.id}",
            f"cae-result:{baseline_result.id}",
            f"cae-study:{candidate.study_id}",
            f"cae-run:{candidate.id}",
            f"cae-result:{candidate_result.id}",
            f"cae-metric:{metric_code}",
        ]
        comparisons.append(
            {
                "metric_code": metric_code,
                "metric_label": METRIC_CATALOG.get(metric_code, {}).get(
                    "label", metric_code.replace("_", " ")
                ),
                "result_type": baseline_result.result_type,
                "unit": baseline_result.unit,
                "baseline": {
                    "result_id": str(baseline_result.id),
                    "value": baseline_result.value,
                    "location": baseline_result.location,
                },
                "candidate": {
                    "result_id": str(candidate_result.id),
                    "value": candidate_result.value,
                    "location": candidate_result.location,
                },
                "delta": round(delta, 6),
                "percent_delta": round(percent_delta, 4) if percent_delta is not None else None,
                "finding": _metric_state(metric_code, delta),
                "interpretation_type": "deterministic_metric_comparison",
                "evidence_refs": evidence_refs,
            }
        )
    return comparisons, metric_incompatibilities


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@transaction.atomic
def compare_cae_runs(baseline: CAERun, candidate: CAERun) -> CAEComparison:
    if baseline.id == candidate.id:
        raise CAEValidationError(
            "VALIDATION_CAE_DISTINCT_RUNS", "Baseline and candidate runs must be different."
        )
    snapshot = {
        "baseline_run_id": str(baseline.id),
        "candidate_run_id": str(candidate.id),
    }
    incompatibilities = evaluate_run_compatibility(baseline, candidate)
    compatible = not incompatibilities
    metrics: list[dict[str, object]] = []
    metric_incompatibilities: list[dict[str, object]] = []
    if compatible:
        metrics, metric_incompatibilities = _metric_comparisons(baseline, candidate)
    counts = {
        state: sum(item["finding"] == state for item in metrics)
        for state in ("improved", "worsened", "unchanged", "changed_review_required")
    }
    comparison = CAEComparison.objects.create(
        baseline_run=baseline,
        candidate_run=candidate,
        compatibility_profile_version=COMPATIBILITY_PROFILE_VERSION,
        request_snapshot=snapshot,
        compatible=compatible,
        incompatibilities=incompatibilities,
    )
    result = {
        "schema_version": "1.0",
        "comparison_id": str(comparison.id),
        "capability": "cae.compare_runs@1.0.0",
        "compatibility_profile_version": COMPATIBILITY_PROFILE_VERSION,
        "compatible": compatible,
        "incompatibilities": incompatibilities,
        "parsed_facts": {
            "baseline": {
                "study_id": str(baseline.study_id),
                "study_code": baseline.study.study_code,
                "run_id": str(baseline.id),
                "run_code": baseline.run_code,
                "input_hash": baseline.input_hash,
            },
            "candidate": {
                "study_id": str(candidate.study_id),
                "study_code": candidate.study.study_code,
                "run_id": str(candidate.id),
                "run_code": candidate.run_code,
                "input_hash": candidate.input_hash,
            },
        },
        "comparison_summary": {
            "comparable_metric_count": len(metrics),
            "excluded_metric_count": len(metric_incompatibilities),
            "finding_counts": counts,
        },
        "metric_comparisons": metrics,
        "metric_incompatibilities": metric_incompatibilities,
        "generated_at": timezone.now().isoformat(),
        "lineage": {
            "comparison_ref": f"cae-comparison:{comparison.id}",
            "baseline_input_hash": baseline.input_hash,
            "candidate_input_hash": candidate.input_hash,
            "compatibility_profile_version": COMPATIBILITY_PROFILE_VERSION,
        },
        "limitations": [
            "Stage 8 uses synthetic structured exports, not an official solver API integration.",
            "Metric deltas are deterministic parsed facts; they do not establish causal effects.",
            (
                "Temperature changes require target-window review and are not labeled "
                "improved/worsened."
            ),
            "No optimization or process-setting recommendation is generated by this capability.",
        ],
    }
    comparison.result = result
    comparison.save(update_fields=["result"])
    AuditEvent.objects.create(
        event_type="cae.comparison_created.v1",
        actor_id="demo-cae-engineer",
        target_refs=[f"cae-comparison:{comparison.id}"],
        detail={
            "compatible": compatible,
            "incompatibility_codes": [item["code"] for item in incompatibilities],
            "comparable_metric_count": len(metrics),
            "compatibility_profile_version": COMPATIBILITY_PROFILE_VERSION,
        },
        payload_hash=_payload_hash(snapshot),
    )
    return comparison
