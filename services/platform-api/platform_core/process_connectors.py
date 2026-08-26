import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from django.db import transaction

from .models import (
    CorrectiveAction,
    DefectObservation,
    ProcessParameter,
    ProcessRun,
    TrialCase,
)

CONNECTOR_KEY = "synthetic-process-trial"
SOURCE_VERSION = "2026.08.1"
MAPPING_VERSION = "process-trial-canonical@1.0.0"


class ProcessTrialConnector(Protocol):
    key: str

    def discover(self) -> list[str]: ...

    def extract(self, source_record_id: str) -> dict[str, object]: ...

    def map(self, raw: dict[str, object]) -> dict[str, object]: ...

    def validate(self, canonical: dict[str, object]) -> list[str]: ...

    def health(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class SeedResult:
    connector_key: str
    source_version: str
    created: int
    existing: int
    case_ids: list[str]


def _parameter(value: float, unit: str) -> dict[str, object]:
    return {"value": value, "unit": unit}


SYNTHETIC_RECORDS: tuple[dict[str, object], ...] = (
    {
        "case_code": "TRIAL-DEMO-001",
        "mold_revision_ref": "DEMO-MOLD-HOUSING-A@R2",
        "part_revision_ref": "DEMO-HOUSING-A@R3",
        "machine_code": "IM-180T",
        "material_code": "PA6-GF30",
        "material_lot": "SYN-PA6-001",
        "product_type": "connector_housing",
        "purpose": "Resolve short shot at the far flow end.",
        "outcome": "resolved",
        "started_at": "2026-01-12T02:00:00+00:00",
        "parameters": {
            "injection_pressure_mpa": _parameter(82, "MPa"),
            "injection_speed_mm_s": _parameter(45, "mm/s"),
            "melt_temperature_c": _parameter(280, "degC"),
            "mold_temperature_c": _parameter(85, "degC"),
            "holding_pressure_mpa": _parameter(55, "MPa"),
            "cooling_time_s": _parameter(22, "s"),
        },
        "defect": {
            "code": "short_shot",
            "severity": "major",
            "location": "far_flow_end",
            "rate": 0.12,
        },
        "action": {
            "code": "increase_injection_pressure",
            "description": (
                "Run a controlled pressure step while monitoring flash and cavity pressure."
            ),
            "before": {"injection_pressure_mpa": _parameter(82, "MPa")},
            "after": {"injection_pressure_mpa": _parameter(92, "MPa")},
            "expected_effect": "Associated historical outcome: improved end-of-fill completion.",
            "stop_condition": (
                "Stop if flash appears or the approved cavity-pressure limit is reached."
            ),
            "defect_rate_before": 0.12,
            "defect_rate_after": 0.02,
        },
    },
    {
        "case_code": "TRIAL-DEMO-002",
        "mold_revision_ref": "DEMO-MOLD-HOUSING-B@R1",
        "part_revision_ref": "DEMO-HOUSING-B@R1",
        "machine_code": "IM-180T",
        "material_code": "PA6-GF30",
        "material_lot": "SYN-PA6-002",
        "product_type": "connector_housing",
        "purpose": "Evaluate short shot response to a bounded speed step.",
        "outcome": "resolved",
        "started_at": "2026-02-04T03:30:00+00:00",
        "parameters": {
            "injection_pressure_mpa": _parameter(88, "MPa"),
            "injection_speed_mm_s": _parameter(38, "mm/s"),
            "melt_temperature_c": _parameter(278, "degC"),
            "mold_temperature_c": _parameter(82, "degC"),
            "holding_pressure_mpa": _parameter(54, "MPa"),
            "cooling_time_s": _parameter(23, "s"),
        },
        "defect": {
            "code": "short_shot",
            "severity": "major",
            "location": "far_flow_end",
            "rate": 0.09,
        },
        "action": {
            "code": "increase_injection_speed",
            "description": "Evaluate one bounded injection-speed step with process monitoring.",
            "before": {"injection_speed_mm_s": _parameter(38, "mm/s")},
            "after": {"injection_speed_mm_s": _parameter(46, "mm/s")},
            "expected_effect": "Associated historical outcome: reduced incomplete fill.",
            "stop_condition": "Stop on burn marks, jetting, flash, or an approved pressure alarm.",
            "defect_rate_before": 0.09,
            "defect_rate_after": 0.03,
        },
    },
    {
        "case_code": "TRIAL-DEMO-003",
        "mold_revision_ref": "DEMO-MOLD-COVER-A@R4",
        "part_revision_ref": "DEMO-COVER-A@R4",
        "machine_code": "IM-120T",
        "material_code": "ABS-GENERAL",
        "material_lot": "SYN-ABS-001",
        "product_type": "electronics_cover",
        "purpose": "Reduce sink mark near a boss.",
        "outcome": "resolved",
        "started_at": "2026-02-18T01:15:00+00:00",
        "parameters": {
            "injection_pressure_mpa": _parameter(70, "MPa"),
            "injection_speed_mm_s": _parameter(52, "mm/s"),
            "melt_temperature_c": _parameter(235, "degC"),
            "mold_temperature_c": _parameter(58, "degC"),
            "holding_pressure_mpa": _parameter(38, "MPa"),
            "holding_time_s": _parameter(5, "s"),
            "cooling_time_s": _parameter(18, "s"),
        },
        "defect": {
            "code": "sink_mark",
            "severity": "moderate",
            "location": "boss_base",
            "rate": 0.14,
        },
        "action": {
            "code": "increase_holding_pressure",
            "description": (
                "Evaluate a bounded holding-pressure step without exceeding the approved window."
            ),
            "before": {"holding_pressure_mpa": _parameter(38, "MPa")},
            "after": {"holding_pressure_mpa": _parameter(45, "MPa")},
            "expected_effect": "Associated historical outcome: reduced boss-base sink visibility.",
            "stop_condition": "Stop on flash, gate stress, or an approved clamp-force alarm.",
            "defect_rate_before": 0.14,
            "defect_rate_after": 0.05,
        },
    },
    {
        "case_code": "TRIAL-DEMO-004",
        "mold_revision_ref": "DEMO-MOLD-TRAY-A@R2",
        "part_revision_ref": "DEMO-TRAY-A@R2",
        "machine_code": "IM-220T",
        "material_code": "PP-HOMO",
        "material_lot": "SYN-PP-001",
        "product_type": "thin_wall_tray",
        "purpose": "Evaluate cooling response for warpage.",
        "outcome": "improved",
        "started_at": "2026-03-06T05:00:00+00:00",
        "parameters": {
            "injection_pressure_mpa": _parameter(64, "MPa"),
            "injection_speed_mm_s": _parameter(72, "mm/s"),
            "melt_temperature_c": _parameter(220, "degC"),
            "mold_temperature_c": _parameter(42, "degC"),
            "holding_pressure_mpa": _parameter(32, "MPa"),
            "cooling_time_s": _parameter(14, "s"),
        },
        "defect": {
            "code": "warpage",
            "severity": "major",
            "location": "long_edge",
            "rate": 0.18,
        },
        "action": {
            "code": "increase_cooling_time",
            "description": (
                "Evaluate a bounded cooling-time step and measure the released-part geometry."
            ),
            "before": {"cooling_time_s": _parameter(14, "s")},
            "after": {"cooling_time_s": _parameter(18, "s")},
            "expected_effect": "Associated historical outcome: lower long-edge distortion.",
            "stop_condition": "Stop if cycle-time constraints are exceeded or distortion worsens.",
            "defect_rate_before": 0.18,
            "defect_rate_after": 0.08,
        },
    },
    {
        "case_code": "TRIAL-DEMO-005",
        "mold_revision_ref": "DEMO-MOLD-HOUSING-C@R1",
        "part_revision_ref": "DEMO-HOUSING-C@R1",
        "machine_code": "IM-120T",
        "material_code": "ABS-GENERAL",
        "material_lot": "SYN-ABS-002",
        "product_type": "electronics_cover",
        "purpose": "Evaluate a flash condition at the parting line.",
        "outcome": "resolved",
        "started_at": "2026-03-22T04:40:00+00:00",
        "parameters": {
            "injection_pressure_mpa": _parameter(86, "MPa"),
            "injection_speed_mm_s": _parameter(68, "mm/s"),
            "melt_temperature_c": _parameter(240, "degC"),
            "mold_temperature_c": _parameter(60, "degC"),
            "holding_pressure_mpa": _parameter(52, "MPa"),
            "cooling_time_s": _parameter(18, "s"),
        },
        "defect": {
            "code": "flash",
            "severity": "major",
            "location": "parting_line",
            "rate": 0.11,
        },
        "action": {
            "code": "reduce_holding_pressure",
            "description": (
                "Evaluate one bounded holding-pressure reduction after tooling inspection."
            ),
            "before": {"holding_pressure_mpa": _parameter(52, "MPa")},
            "after": {"holding_pressure_mpa": _parameter(46, "MPa")},
            "expected_effect": "Associated historical outcome: lower parting-line flash rate.",
            "stop_condition": "Stop if sink, short shot, or dimensional nonconformance appears.",
            "defect_rate_before": 0.11,
            "defect_rate_after": 0.03,
        },
    },
    {
        "case_code": "TRIAL-DEMO-006",
        "mold_revision_ref": "DEMO-MOLD-HOUSING-D@R1",
        "part_revision_ref": "DEMO-HOUSING-D@R1",
        "machine_code": "IM-120T",
        "material_code": "ABS-GENERAL",
        "material_lot": "SYN-ABS-003",
        "product_type": "connector_housing",
        "purpose": "Record an unresolved short-shot trial for negative evidence.",
        "outcome": "not_resolved",
        "started_at": "2026-04-02T07:10:00+00:00",
        "parameters": {
            "injection_pressure_mpa": _parameter(76, "MPa"),
            "injection_speed_mm_s": _parameter(42, "mm/s"),
            "melt_temperature_c": _parameter(232, "degC"),
            "mold_temperature_c": _parameter(55, "degC"),
            "holding_pressure_mpa": _parameter(40, "MPa"),
            "cooling_time_s": _parameter(20, "s"),
        },
        "defect": {
            "code": "short_shot",
            "severity": "major",
            "location": "far_flow_end",
            "rate": 0.10,
        },
        "action": {
            "code": "increase_melt_temperature",
            "description": (
                "Historical unsuccessful temperature step retained as negative evidence."
            ),
            "before": {"melt_temperature_c": _parameter(232, "degC")},
            "after": {"melt_temperature_c": _parameter(240, "degC")},
            "expected_effect": "No demonstrated improvement in this synthetic record.",
            "stop_condition": "Stop at the material supplier's approved temperature limit.",
            "defect_rate_before": 0.10,
            "defect_rate_after": 0.10,
        },
    },
)


class SyntheticProcessTrialConnector:
    key = CONNECTOR_KEY

    def discover(self) -> list[str]:
        return [str(record["case_code"]) for record in SYNTHETIC_RECORDS]

    def extract(self, source_record_id: str) -> dict[str, object]:
        for record in SYNTHETIC_RECORDS:
            if record["case_code"] == source_record_id:
                return json.loads(json.dumps(record))
        raise KeyError(source_record_id)

    def map(self, raw: dict[str, object]) -> dict[str, object]:
        return raw

    def validate(self, canonical: dict[str, object]) -> list[str]:
        required = {
            "case_code",
            "machine_code",
            "material_code",
            "product_type",
            "parameters",
            "defect",
            "action",
        }
        missing = sorted(required - canonical.keys())
        return [f"missing:{field}" for field in missing]

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "connector_key": self.key,
            "source_version": SOURCE_VERSION,
            "record_count": len(SYNTHETIC_RECORDS),
            "source_type": "synthetic",
        }


def _hash_record(record: dict[str, object]) -> str:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@transaction.atomic
def seed_demo_process_trials(
    connector: ProcessTrialConnector | None = None,
) -> SeedResult:
    selected = connector or SyntheticProcessTrialConnector()
    created_count = 0
    existing_count = 0
    case_ids: list[str] = []
    for source_record_id in selected.discover():
        raw = selected.extract(source_record_id)
        canonical = selected.map(raw)
        errors = selected.validate(canonical)
        if errors:
            raise ValueError(f"Connector record {source_record_id} is invalid: {', '.join(errors)}")
        source_hash = _hash_record(raw)
        trial, created = TrialCase.objects.get_or_create(
            connector_key=selected.key,
            source_record_id=source_record_id,
            source_version=SOURCE_VERSION,
            defaults={
                "case_code": canonical["case_code"],
                "source_hash": source_hash,
                "mapping_version": MAPPING_VERSION,
                "classification": "public_demo",
                "acl_scopes": ["public-demo"],
                "mold_revision_ref": canonical["mold_revision_ref"],
                "part_revision_ref": canonical["part_revision_ref"],
                "machine_code": canonical["machine_code"],
                "material_code": canonical["material_code"],
                "material_lot": canonical["material_lot"],
                "product_type": canonical["product_type"],
                "purpose": canonical["purpose"],
                "outcome": canonical["outcome"],
                "started_at": datetime.fromisoformat(str(canonical["started_at"])),
                "data_quality": {
                    "status": "complete_synthetic_fixture",
                    "missing_fields": [],
                    "not_production_ground_truth": True,
                },
            },
        )
        if not created:
            if trial.source_hash != source_hash:
                raise ValueError(
                    f"Connector record {source_record_id} changed without a source version bump."
                )
            existing_count += 1
            case_ids.append(str(trial.id))
            continue
        created_count += 1
        run = ProcessRun.objects.create(
            trial=trial,
            run_number=1,
            cycle_start=1,
            cycle_end=30,
            environment={"ambient_temperature_c": 24, "humidity_percent": 55},
            result=str(canonical["outcome"]),
            data_quality={"status": "complete_synthetic_fixture", "sampling": "single_setpoint"},
        )
        for code, measurement in dict(canonical["parameters"]).items():
            values = dict(measurement)
            ProcessParameter.objects.create(
                process_run=run,
                canonical_code=code,
                raw_name=code.replace("_", " "),
                value=values["value"],
                unit=values["unit"],
                value_kind=ProcessParameter.ValueKind.SETPOINT,
                sampling_method="synthetic_record",
            )
        defect = dict(canonical["defect"])
        defect_ref = f"{trial.case_code}:run:1:defect:{defect['code']}"
        DefectObservation.objects.create(
            process_run=run,
            defect_code=defect["code"],
            severity=defect["severity"],
            location=defect["location"],
            quantity_rate=defect["rate"],
            quantity_unit="fraction",
            inspection_method="synthetic_visual_inspection",
            evidence_refs=[defect_ref],
        )
        action = dict(canonical["action"])
        action_ref = f"{trial.case_code}:run:1:action:{action['code']}"
        CorrectiveAction.objects.create(
            process_run=run,
            action_code=action["code"],
            description=action["description"],
            before_values=action["before"],
            after_values=action["after"],
            rationale_source={
                "type": "synthetic_fixture",
                "source_record_id": source_record_id,
                "source_version": SOURCE_VERSION,
            },
            approved_by="synthetic-demo-approval",
            executed=True,
            observed_outcome={
                "trial_outcome": canonical["outcome"],
                "defect_rate_before": action["defect_rate_before"],
                "defect_rate_after": action["defect_rate_after"],
            },
            expected_effect=action["expected_effect"],
            stop_condition=action["stop_condition"],
            evidence_refs=[action_ref, defect_ref],
        )
        case_ids.append(str(trial.id))
    return SeedResult(selected.key, SOURCE_VERSION, created_count, existing_count, case_ids)
