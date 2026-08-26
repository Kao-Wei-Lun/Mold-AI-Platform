import hashlib
import json
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, ProcessCaseSearch, ProcessRun, TrialCase

SCORING_PROFILE_VERSION = "process-case-demo@1.0.0"
SUPPORTED_DEFECTS = {"flash", "short_shot", "sink_mark", "warpage"}
PARAMETER_SPECS: dict[str, dict[str, object]] = {
    "injection_pressure_mpa": {"unit": "MPa", "minimum": 20.0, "maximum": 300.0},
    "injection_speed_mm_s": {"unit": "mm/s", "minimum": 1.0, "maximum": 500.0},
    "melt_temperature_c": {"unit": "degC", "minimum": 100.0, "maximum": 450.0},
    "mold_temperature_c": {"unit": "degC", "minimum": 0.0, "maximum": 200.0},
    "holding_pressure_mpa": {"unit": "MPa", "minimum": 5.0, "maximum": 250.0},
    "holding_time_s": {"unit": "s", "minimum": 0.0, "maximum": 120.0},
    "cooling_time_s": {"unit": "s", "minimum": 0.0, "maximum": 300.0},
}
LANE_WEIGHTS = {
    "defect": 0.35,
    "material": 0.20,
    "machine": 0.15,
    "product_type": 0.10,
    "location": 0.05,
    "parameters": 0.15,
}


class ProcessTrialValidationError(ValueError):
    def __init__(self, code: str, user_message: str) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


@dataclass(frozen=True)
class ProcessQuery:
    defect_code: str
    material_code: str
    machine_code: str
    product_type: str
    location: str
    parameters: dict[str, dict[str, object]]
    top_k: int

    def snapshot(self) -> dict[str, object]:
        return {
            "defect_code": self.defect_code,
            "material_code": self.material_code,
            "machine_code": self.machine_code,
            "product_type": self.product_type,
            "location": self.location,
            "parameters": self.parameters,
            "top_k": self.top_k,
        }


def _normalized_code(value: object, *, maximum: int = 128) -> str:
    return str(value or "").strip()[:maximum]


def parse_process_query(payload: object) -> ProcessQuery:
    if not isinstance(payload, dict):
        raise ProcessTrialValidationError(
            "VALIDATION_PROCESS_QUERY", "The request body must be a JSON object."
        )
    defect_code = _normalized_code(payload.get("defect_code"), maximum=64)
    if not defect_code:
        raise ProcessTrialValidationError("VALIDATION_DEFECT_REQUIRED", "defect_code is required.")
    if defect_code not in SUPPORTED_DEFECTS:
        raise ProcessTrialValidationError(
            "VALIDATION_DEFECT_CODE",
            f"defect_code must be one of: {', '.join(sorted(SUPPORTED_DEFECTS))}.",
        )
    try:
        top_k = int(payload.get("top_k", 5))
    except (TypeError, ValueError) as exc:
        raise ProcessTrialValidationError("VALIDATION_TOP_K", "top_k must be an integer.") from exc
    if top_k < 1 or top_k > 10:
        raise ProcessTrialValidationError("VALIDATION_TOP_K", "top_k must be between 1 and 10.")

    raw_parameters = payload.get("parameters", {})
    if raw_parameters is None:
        raw_parameters = {}
    if not isinstance(raw_parameters, dict):
        raise ProcessTrialValidationError(
            "VALIDATION_PROCESS_PARAMETERS", "parameters must be an object."
        )
    parameters: dict[str, dict[str, object]] = {}
    for code, raw_measurement in raw_parameters.items():
        if code not in PARAMETER_SPECS:
            raise ProcessTrialValidationError(
                "VALIDATION_PARAMETER_CODE", f"Unsupported canonical parameter code: {code}."
            )
        if not isinstance(raw_measurement, dict):
            raise ProcessTrialValidationError(
                "VALIDATION_PROCESS_PARAMETERS", f"parameters.{code} must be an object."
            )
        spec = PARAMETER_SPECS[code]
        unit = str(raw_measurement.get("unit", "")).strip()
        if unit != spec["unit"]:
            raise ProcessTrialValidationError(
                "VALIDATION_PARAMETER_UNIT",
                f"parameters.{code}.unit must be {spec['unit']}.",
            )
        try:
            value = float(raw_measurement["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProcessTrialValidationError(
                "VALIDATION_PARAMETER_VALUE",
                f"parameters.{code}.value must be numeric.",
            ) from exc
        parameters[code] = {"value": value, "unit": unit}

    return ProcessQuery(
        defect_code=defect_code,
        material_code=_normalized_code(payload.get("material_code"), maximum=64),
        machine_code=_normalized_code(payload.get("machine_code"), maximum=64),
        product_type=_normalized_code(payload.get("product_type")),
        location=_normalized_code(payload.get("location")),
        parameters=parameters,
        top_k=top_k,
    )


def _parameter_payload(run: ProcessRun) -> dict[str, dict[str, object]]:
    return {
        item.canonical_code: {
            "value": item.value,
            "unit": item.unit,
            "value_kind": item.value_kind,
            "sampling_method": item.sampling_method,
        }
        for item in run.parameters.all()
    }


def trial_case_payload(trial: TrialCase) -> dict[str, object]:
    runs = []
    for run in trial.runs.all():
        runs.append(
            {
                "process_run_id": str(run.id),
                "run_number": run.run_number,
                "cycle_range": {"start": run.cycle_start, "end": run.cycle_end},
                "parameters": _parameter_payload(run),
                "environment": run.environment,
                "result": run.result,
                "data_quality": run.data_quality,
                "defects": [
                    {
                        "defect_id": str(item.id),
                        "defect_code": item.defect_code,
                        "severity": item.severity,
                        "location": item.location,
                        "quantity_rate": item.quantity_rate,
                        "quantity_unit": item.quantity_unit,
                        "inspection_method": item.inspection_method,
                        "evidence_refs": item.evidence_refs,
                    }
                    for item in run.defects.all()
                ],
                "corrective_actions": [
                    {
                        "action_id": str(item.id),
                        "action_code": item.action_code,
                        "description": item.description,
                        "before_values": item.before_values,
                        "after_values": item.after_values,
                        "rationale_source": item.rationale_source,
                        "approved_by": item.approved_by,
                        "executed": item.executed,
                        "observed_outcome": item.observed_outcome,
                        "expected_effect": item.expected_effect,
                        "stop_condition": item.stop_condition,
                        "evidence_refs": item.evidence_refs,
                    }
                    for item in run.actions.all()
                ],
            }
        )
    return {
        "trial_case_id": str(trial.id),
        "case_code": trial.case_code,
        "mold_revision_ref": trial.mold_revision_ref,
        "part_revision_ref": trial.part_revision_ref,
        "machine_code": trial.machine_code,
        "material_code": trial.material_code,
        "material_lot": trial.material_lot,
        "product_type": trial.product_type,
        "purpose": trial.purpose,
        "outcome": trial.outcome,
        "started_at": trial.started_at.isoformat(),
        "classification": trial.classification,
        "acl_scopes": trial.acl_scopes,
        "data_quality": trial.data_quality,
        "provenance": {
            "connector_key": trial.connector_key,
            "source_record_id": trial.source_record_id,
            "source_version": trial.source_version,
            "source_hash": trial.source_hash,
            "mapping_version": trial.mapping_version,
            "source_type": "synthetic",
        },
        "runs": runs,
    }


def trial_case_queryset():
    return TrialCase.objects.filter(classification="public_demo").prefetch_related(
        "runs__parameters", "runs__defects", "runs__actions"
    )


def _parameter_similarity(
    query_parameters: dict[str, dict[str, object]], candidate_parameters: dict[str, Any]
) -> tuple[float, list[dict[str, object]], list[dict[str, object]]]:
    scores: list[float] = []
    similarities: list[dict[str, object]] = []
    differences: list[dict[str, object]] = []
    for code, query_measurement in query_parameters.items():
        candidate = candidate_parameters.get(code)
        if not candidate:
            differences.append({"factor": code, "reason": "candidate_value_missing"})
            continue
        spec = PARAMETER_SPECS[code]
        span = float(spec["maximum"]) - float(spec["minimum"])
        delta = abs(float(query_measurement["value"]) - float(candidate["value"]))
        score = max(0.0, 1.0 - (delta / span))
        scores.append(score)
        evidence = {
            "factor": code,
            "query": query_measurement,
            "candidate": {"value": candidate["value"], "unit": candidate["unit"]},
            "absolute_delta": round(delta, 4),
            "normalized_similarity": round(score, 4),
        }
        if score >= 0.9:
            similarities.append(evidence)
        else:
            differences.append(evidence)
    return (sum(scores) / len(scores) if scores else 0.0), similarities, differences


def _score_case(query: ProcessQuery, trial: TrialCase) -> dict[str, object] | None:
    run = trial.runs.first()
    if run is None:
        return None
    defect = run.defects.first()
    if defect is None:
        return None
    candidate_parameters = _parameter_payload(run)
    parameter_score, parameter_similarities, parameter_differences = _parameter_similarity(
        query.parameters, candidate_parameters
    )
    values: dict[str, float] = {"defect": float(defect.defect_code == query.defect_code)}
    similarities: list[dict[str, object]] = []
    differences: list[dict[str, object]] = []

    def add_exact_lane(lane: str, query_value: str, candidate_value: str) -> None:
        if not query_value:
            return
        match = query_value.casefold() == candidate_value.casefold()
        values[lane] = float(match)
        target = similarities if match else differences
        target.append(
            {"factor": lane, "query": query_value, "candidate": candidate_value, "match": match}
        )

    add_exact_lane("material", query.material_code, trial.material_code)
    add_exact_lane("machine", query.machine_code, trial.machine_code)
    add_exact_lane("product_type", query.product_type, trial.product_type)
    add_exact_lane("location", query.location, defect.location)
    if query.parameters:
        values["parameters"] = parameter_score
        similarities.extend(parameter_similarities)
        differences.extend(parameter_differences)
    if values["defect"]:
        similarities.insert(
            0,
            {
                "factor": "defect",
                "query": query.defect_code,
                "candidate": defect.defect_code,
                "match": True,
            },
        )
    else:
        differences.insert(
            0,
            {
                "factor": "defect",
                "query": query.defect_code,
                "candidate": defect.defect_code,
                "match": False,
            },
        )
    active_weight = sum(LANE_WEIGHTS[lane] for lane in values)
    score = sum(values[lane] * LANE_WEIGHTS[lane] for lane in values) / active_weight
    action = run.actions.first()
    evidence_refs = [f"trial-case:{trial.id}", f"process-run:{run.id}"]
    if defect:
        evidence_refs.extend(defect.evidence_refs)
    if action:
        evidence_refs.extend(action.evidence_refs)
    return {
        "trial_case_id": str(trial.id),
        "case_code": trial.case_code,
        "score": round(score, 4),
        "score_breakdown": {lane: round(value, 4) for lane, value in values.items()},
        "profile_version": SCORING_PROFILE_VERSION,
        "material_code": trial.material_code,
        "machine_code": trial.machine_code,
        "product_type": trial.product_type,
        "mold_revision_ref": trial.mold_revision_ref,
        "defect": {
            "code": defect.defect_code,
            "severity": defect.severity,
            "location": defect.location,
            "quantity_rate": defect.quantity_rate,
            "quantity_unit": defect.quantity_unit,
        },
        "parameters": candidate_parameters,
        "corrective_action": (
            {
                "action_id": str(action.id),
                "action_code": action.action_code,
                "description": action.description,
                "before_values": action.before_values,
                "after_values": action.after_values,
                "observed_outcome": action.observed_outcome,
                "expected_effect": action.expected_effect,
                "stop_condition": action.stop_condition,
            }
            if action
            else None
        ),
        "outcome": trial.outcome,
        "similarities": similarities,
        "differences": differences,
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
        "provenance": {
            "connector_key": trial.connector_key,
            "source_record_id": trial.source_record_id,
            "source_version": trial.source_version,
            "source_hash": trial.source_hash,
            "source_type": "synthetic",
        },
        "data_quality": trial.data_quality,
    }


def _rule_findings(query: ProcessQuery) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for code, measurement in query.parameters.items():
        spec = PARAMETER_SPECS[code]
        value = float(measurement["value"])
        minimum = float(spec["minimum"])
        maximum = float(spec["maximum"])
        if value < minimum or value > maximum:
            findings.append(
                {
                    "code": "OUTSIDE_DEMO_VALIDATION_BOUND",
                    "parameter_code": code,
                    "actual": measurement,
                    "allowed_validation_bound": {
                        "minimum": minimum,
                        "maximum": maximum,
                        "unit": spec["unit"],
                    },
                    "severity": "blocking",
                    "source": "demo-input-validation@1.0.0",
                }
            )
    return findings


def _recommendation(
    query: ProcessQuery, ranked: list[dict[str, object]], rule_findings: list[dict[str, object]]
) -> dict[str, object]:
    missing = [
        field
        for field, value in (
            ("material_code", query.material_code),
            ("machine_code", query.machine_code),
        )
        if not value
    ]
    if missing:
        return {
            "abstained": True,
            "reason_code": "MISSING_COMPATIBILITY_CONTEXT",
            "message": f"Add {', '.join(missing)} before requesting parameter ranges.",
            "required_fields": missing,
            "controlled_trial_steps": [],
        }
    if rule_findings:
        return {
            "abstained": True,
            "reason_code": "INPUT_OUTSIDE_DEMO_VALIDATION_BOUND",
            "message": "Correct or approve out-of-bound inputs before using case-based ranges.",
            "required_fields": [],
            "controlled_trial_steps": [],
        }
    compatible = [
        item
        for item in ranked
        if item["score_breakdown"].get("defect") == 1.0
        and item["score_breakdown"].get("material") == 1.0
        and item["score_breakdown"].get("machine") == 1.0
        and item["outcome"] in {"resolved", "improved"}
        and item["corrective_action"]
    ]
    if not compatible:
        return {
            "abstained": True,
            "reason_code": "NO_COMPATIBLE_SUCCESSFUL_CASE",
            "message": "No successful case matches defect, material, and machine compatibility.",
            "required_fields": [],
            "controlled_trial_steps": [],
        }
    steps = []
    seen_actions: set[str] = set()
    for item in compatible:
        action = item["corrective_action"]
        action_code = str(action["action_code"])
        if action_code in seen_actions:
            continue
        seen_actions.add(action_code)
        steps.append(
            {
                "rank": len(steps) + 1,
                "action_code": action_code,
                "instruction": action["description"],
                "historical_before": action["before_values"],
                "historical_after": action["after_values"],
                "expected_effect": action["expected_effect"],
                "stop_condition": action["stop_condition"],
                "confidence": {
                    "label": "case_association_only",
                    "score": round(float(item["score"]) * 0.85, 4),
                    "basis": "deterministic similarity multiplied by a conservative Demo factor",
                },
                "source_case_code": item["case_code"],
                "evidence_refs": item["evidence_refs"],
                "requires_engineer_approval": True,
                "do_not_auto_apply": True,
            }
        )
        if len(steps) == 3:
            break
    return {
        "abstained": False,
        "reason_code": None,
        "message": "Historical ranges are candidates for an engineer-approved controlled trial.",
        "required_fields": [],
        "controlled_trial_steps": steps,
    }


def _payload_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


@transaction.atomic
def search_process_cases(payload: object) -> ProcessCaseSearch:
    query = parse_process_query(payload)
    snapshot = query.snapshot()
    missing_material = not query.material_code
    findings = _rule_findings(query)
    ranked: list[dict[str, object]] = []
    if not missing_material:
        for trial in trial_case_queryset():
            if "public-demo" not in trial.acl_scopes:
                continue
            scored = _score_case(query, trial)
            if scored is not None:
                ranked.append(scored)
        ranked.sort(key=lambda item: (-float(item["score"]), str(item["case_code"])))
        ranked = ranked[: query.top_k]
        for rank, item in enumerate(ranked, start=1):
            item["rank"] = rank

    recommendation = _recommendation(query, ranked, findings)
    if missing_material:
        recommendation = {
            "abstained": True,
            "reason_code": "MISSING_COMPATIBILITY_CONTEXT",
            "message": "Add material_code before retrieving cases or parameter ranges.",
            "required_fields": ["material_code"],
            "controlled_trial_steps": [],
        }
    abstained = bool(recommendation["abstained"])
    now = timezone.now().isoformat()
    result = {
        "schema_version": "1.0",
        "capability": "process.case_search@1.0.0",
        "scoring_profile_version": SCORING_PROFILE_VERSION,
        "query": snapshot,
        "result_count": len(ranked),
        "results": ranked,
        "rule_findings": findings,
        "recommendation": recommendation,
        "abstained": abstained,
        "retrieved_at": now,
        "principal_scope_source": "server_demo_policy",
        "lineage": {
            "connector_key": "synthetic-process-trial",
            "source_type": "synthetic",
            "mapping_version": "process-trial-canonical@1.0.0",
            "scoring_profile_version": SCORING_PROFILE_VERSION,
        },
        "limitations": [
            "All Stage 7 cases and outcomes are synthetic fixtures, not production evidence.",
            (
                "Similarity and outcome association do not establish root-cause or "
                "treatment causality."
            ),
            (
                "Historical ranges require engineer review, an approved process window, "
                "and a controlled trial."
            ),
            "This capability never writes settings to MES, PLC, or molding machines.",
        ],
    }
    search = ProcessCaseSearch.objects.create(
        request_snapshot=snapshot,
        scoring_profile_version=SCORING_PROFILE_VERSION,
        result=result,
        abstained=abstained,
    )
    result["search_id"] = str(search.id)
    result["lineage"]["search_ref"] = f"process-case-search:{search.id}"
    search.result = result
    search.save(update_fields=["result"])
    AuditEvent.objects.create(
        event_type="process.case_search.v1",
        actor_id="demo-engineer",
        target_refs=[f"process-case-search:{search.id}"],
        detail={
            "scoring_profile_version": SCORING_PROFILE_VERSION,
            "result_count": len(ranked),
            "abstained": abstained,
            "recommendation_reason_code": recommendation["reason_code"],
        },
        payload_hash=_payload_hash(snapshot),
    )
    return search
