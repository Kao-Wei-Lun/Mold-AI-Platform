import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from django.db import transaction

from .models import CAEResult, CAERun, CAEStudy

CONNECTOR_KEY = "synthetic-cae-structured-export"
SOURCE_VERSION = "2026.08.1"
MAPPING_VERSION = "cae-canonical@1.0.0"
INTEGRATION_LEVEL = "synthetic_structured_export"


class CAEConnector(Protocol):
    key: str

    def discover(self) -> list[str]: ...

    def extract(self, source_record_id: str) -> dict[str, object]: ...

    def map(self, raw: dict[str, object]) -> dict[str, object]: ...

    def validate(self, canonical: dict[str, object]) -> list[str]: ...

    def health(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class CAESeedResult:
    connector_key: str
    source_version: str
    created: int
    existing: int
    study_ids: list[str]


def _result(
    metric_code: str,
    value: float,
    unit: str,
    *,
    result_type: str = "scalar",
    location: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "metric_code": metric_code,
        "result_type": result_type,
        "value": value,
        "unit": unit,
        "location": location or {"scope": "whole_part"},
        "field_summary": {"aggregation": "synthetic_exported_summary"},
        "quality_flags": [],
    }


def _record(
    study_code: str,
    *,
    solver_version: str = "2026.1",
    material_model_code: str = "PA6-GF30-DEMO@1",
    mesh_checksum: str = "a" * 64,
    fill_time: float,
    pressure: float,
    temperature: float,
    weld_lines: int,
    air_traps: int,
    warpage: float,
    injection_time: float,
) -> dict[str, object]:
    return {
        "study_code": study_code,
        "solver_name": "Moldflow-like Demo Solver",
        "product_ref": "DEMO-CONNECTOR-HOUSING@R3",
        "mold_revision_ref": "DEMO-MOLD-HOUSING-A@R2",
        "material_model_code": material_model_code,
        "mesh_family": "DEMO-HOUSING-A-TETRA",
        "objective": "Compare fill, pressure, temperature, defect indicators, and warpage.",
        "owner": "demo-cae-engineer",
        "run": {
            "run_code": "RUN-001",
            "solver_name": "Moldflow-like Demo Solver",
            "solver_version": solver_version,
            "mesh_artifact_ref": f"synthetic-mesh:{mesh_checksum[:12]}",
            "mesh_checksum": mesh_checksum,
            "material_model_code": material_model_code,
            "boundary_settings": {
                "gate_definition": "single_center_gate@1",
                "coolant_profile": "demo-standard@1",
            },
            "process_settings": {
                "injection_time_s": injection_time,
                "melt_temperature_c": 280,
                "mold_temperature_c": 85,
            },
            "unit_system": "SI",
            "status": "succeeded",
            "results": [
                _result("fill_time_s", fill_time, "s"),
                _result(
                    "max_injection_pressure_mpa",
                    pressure,
                    "MPa",
                    location={"scope": "node", "node_ref": "N-PRESSURE-MAX"},
                ),
                _result(
                    "min_melt_front_temperature_c",
                    temperature,
                    "degC",
                    location={"scope": "region", "region_ref": "far_flow_end"},
                ),
                _result(
                    "weld_line_count",
                    weld_lines,
                    "count",
                    result_type="region_count",
                    location={"scope": "regions", "region_refs": ["WL-01", "WL-02"]},
                ),
                _result(
                    "air_trap_count",
                    air_traps,
                    "count",
                    result_type="region_count",
                    location={"scope": "regions", "region_refs": ["AT-01", "AT-02"]},
                ),
                _result(
                    "max_warpage_mm",
                    warpage,
                    "mm",
                    location={"scope": "node", "node_ref": "N-WARP-MAX"},
                ),
            ],
        },
    }


SYNTHETIC_CAE_RECORDS: tuple[dict[str, object], ...] = (
    _record(
        "CAE-DEMO-BASELINE",
        fill_time=1.42,
        pressure=95.0,
        temperature=252.0,
        weld_lines=4,
        air_traps=7,
        warpage=0.42,
        injection_time=1.2,
    ),
    _record(
        "CAE-DEMO-CANDIDATE",
        fill_time=1.31,
        pressure=89.0,
        temperature=255.0,
        weld_lines=3,
        air_traps=5,
        warpage=0.36,
        injection_time=1.1,
    ),
    _record(
        "CAE-DEMO-INCOMPATIBLE-SOLVER",
        solver_version="2025.2",
        fill_time=1.28,
        pressure=87.0,
        temperature=254.0,
        weld_lines=3,
        air_traps=4,
        warpage=0.34,
        injection_time=1.05,
    ),
    _record(
        "CAE-DEMO-INCOMPATIBLE-MATERIAL",
        material_model_code="PA6-GF30-DEMO@2",
        fill_time=1.25,
        pressure=85.0,
        temperature=256.0,
        weld_lines=2,
        air_traps=4,
        warpage=0.33,
        injection_time=1.0,
    ),
    _record(
        "CAE-DEMO-INCOMPATIBLE-MESH",
        mesh_checksum="b" * 64,
        fill_time=1.29,
        pressure=88.0,
        temperature=255.0,
        weld_lines=3,
        air_traps=4,
        warpage=0.35,
        injection_time=1.08,
    ),
)


class SyntheticCAEConnector:
    key = CONNECTOR_KEY

    def discover(self) -> list[str]:
        return [str(record["study_code"]) for record in SYNTHETIC_CAE_RECORDS]

    def extract(self, source_record_id: str) -> dict[str, object]:
        for record in SYNTHETIC_CAE_RECORDS:
            if record["study_code"] == source_record_id:
                return json.loads(json.dumps(record))
        raise KeyError(source_record_id)

    def map(self, raw: dict[str, object]) -> dict[str, object]:
        return raw

    def validate(self, canonical: dict[str, object]) -> list[str]:
        required = {
            "study_code",
            "solver_name",
            "mold_revision_ref",
            "material_model_code",
            "mesh_family",
            "run",
        }
        errors = [f"missing:{field}" for field in sorted(required - canonical.keys())]
        run = canonical.get("run")
        if isinstance(run, dict) and not run.get("results"):
            errors.append("missing:run.results")
        return errors

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "connector_key": self.key,
            "source_version": SOURCE_VERSION,
            "record_count": len(SYNTHETIC_CAE_RECORDS),
            "integration_level": INTEGRATION_LEVEL,
            "official_solver_api_connected": False,
        }


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@transaction.atomic
def seed_demo_cae_studies(connector: CAEConnector | None = None) -> CAESeedResult:
    selected = connector or SyntheticCAEConnector()
    created_count = 0
    existing_count = 0
    study_ids: list[str] = []
    for source_record_id in selected.discover():
        raw = selected.extract(source_record_id)
        canonical = selected.map(raw)
        errors = selected.validate(canonical)
        if errors:
            raise ValueError(f"Connector record {source_record_id} is invalid: {', '.join(errors)}")
        source_hash = _hash_payload(raw)
        study, created = CAEStudy.objects.get_or_create(
            connector_key=selected.key,
            source_record_id=source_record_id,
            source_version=SOURCE_VERSION,
            defaults={
                "study_code": canonical["study_code"],
                "integration_level": INTEGRATION_LEVEL,
                "source_hash": source_hash,
                "mapping_version": MAPPING_VERSION,
                "solver_name": canonical["solver_name"],
                "product_ref": canonical["product_ref"],
                "mold_revision_ref": canonical["mold_revision_ref"],
                "material_model_code": canonical["material_model_code"],
                "mesh_family": canonical["mesh_family"],
                "objective": canonical["objective"],
                "owner": canonical["owner"],
                "classification": "public_demo",
                "acl_scopes": ["public-demo"],
                "data_quality": {
                    "status": "complete_synthetic_fixture",
                    "not_solver_ground_truth": True,
                },
            },
        )
        if not created:
            if study.source_hash != source_hash:
                raise ValueError(
                    f"Connector record {source_record_id} changed without a source version bump."
                )
            existing_count += 1
            study_ids.append(str(study.id))
            continue
        created_count += 1
        raw_run = dict(canonical["run"])
        input_payload = {
            key: raw_run[key]
            for key in (
                "solver_name",
                "solver_version",
                "mesh_checksum",
                "material_model_code",
                "boundary_settings",
                "process_settings",
                "unit_system",
            )
        }
        run = CAERun.objects.create(
            study=study,
            run_code=raw_run["run_code"],
            solver_name=raw_run["solver_name"],
            solver_version=raw_run["solver_version"],
            mesh_artifact_ref=raw_run["mesh_artifact_ref"],
            mesh_checksum=raw_run["mesh_checksum"],
            material_model_code=raw_run["material_model_code"],
            boundary_settings=raw_run["boundary_settings"],
            process_settings=raw_run["process_settings"],
            unit_system=raw_run["unit_system"],
            status=raw_run["status"],
            input_hash=_hash_payload(input_payload),
            data_quality={"status": "complete_synthetic_fixture"},
        )
        for ordinal, raw_result in enumerate(raw_run["results"], start=1):
            result = dict(raw_result)
            CAEResult.objects.create(
                run=run,
                metric_code=result["metric_code"],
                result_type=result["result_type"],
                value=result["value"],
                unit=result["unit"],
                location=result["location"],
                field_summary=result["field_summary"],
                quality_flags=result["quality_flags"],
                parser_name="synthetic-cae-json-parser",
                parser_version="1.0.0",
                source_locator={
                    "source_record_id": source_record_id,
                    "json_path": f"$.run.results[{ordinal - 1}]",
                },
            )
        study_ids.append(str(study.id))
    return CAESeedResult(selected.key, SOURCE_VERSION, created_count, existing_count, study_ids)
