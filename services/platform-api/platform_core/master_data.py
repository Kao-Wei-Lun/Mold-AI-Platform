from __future__ import annotations

from collections import Counter
from typing import Any

from django.core.cache import cache

from .models import (
    Artifact,
    DataScope,
    DefectObservation,
    MasterDataItem,
    Mold,
    ProcessParameter,
    TrialCase,
)

MASTER_DATA_CACHE_KEY = "mold-ai:master-data-options:v2"
MASTER_DATA_KINDS = {choice for choice, _ in MasterDataItem.Kind.choices}

MASTER_DATA_SEED: tuple[dict[str, Any], ...] = (
    {
        "kind": "dataset",
        "code": "public-demo-v1",
        "name_en": "Public Demo",
        "name_zh_tw": "公開 Demo",
        "sort_order": 10,
    },
    {
        "kind": "dataset",
        "code": "curated-cad-demo-v1",
        "name_en": "Curated CAD Demo",
        "name_zh_tw": "精選 CAD Demo",
        "sort_order": 20,
    },
    {
        "kind": "dataset",
        "code": "manual-cad-upload-v1",
        "name_en": "Manual CAD uploads",
        "name_zh_tw": "手動 CAD 上傳",
        "sort_order": 30,
        "attributes": {"purpose": "cad_upload", "default": True},
    },
    {
        "kind": "product_type",
        "code": "housing",
        "name_en": "Housing",
        "name_zh_tw": "外殼",
        "sort_order": 10,
    },
    {
        "kind": "product_type",
        "code": "connector_housing",
        "name_en": "Connector housing",
        "name_zh_tw": "連接器外殼",
        "sort_order": 20,
    },
    {
        "kind": "product_type",
        "code": "electronics_cover",
        "name_en": "Electronics cover",
        "name_zh_tw": "電子產品上蓋",
        "sort_order": 30,
    },
    {
        "kind": "product_type",
        "code": "thin_wall_tray",
        "name_en": "Thin-wall tray",
        "name_zh_tw": "薄壁托盤",
        "sort_order": 40,
    },
    {
        "kind": "material",
        "code": "PA6-GF30",
        "name_en": "PA6 GF30",
        "name_zh_tw": "PA6 玻纖 30%",
        "sort_order": 10,
        "attributes": {"family": "PA6", "grade": "GF30"},
    },
    {
        "kind": "material",
        "code": "ABS-GENERAL",
        "name_en": "General ABS",
        "name_zh_tw": "通用 ABS",
        "sort_order": 20,
        "attributes": {"family": "ABS"},
    },
    {
        "kind": "material",
        "code": "PP-HOMO",
        "name_en": "PP homopolymer",
        "name_zh_tw": "PP 均聚物",
        "sort_order": 30,
        "attributes": {"family": "PP"},
    },
    {
        "kind": "material",
        "code": "PC_ABS",
        "name_en": "PC/ABS",
        "name_zh_tw": "PC/ABS 合金",
        "sort_order": 40,
        "attributes": {"family": "PC/ABS"},
    },
    {
        "kind": "machine",
        "code": "IM-120T",
        "name_en": "Injection machine 120T",
        "name_zh_tw": "120 噸射出機",
        "sort_order": 10,
        "attributes": {"tonnage": 120},
    },
    {
        "kind": "machine",
        "code": "IM-180T",
        "name_en": "Injection machine 180T",
        "name_zh_tw": "180 噸射出機",
        "sort_order": 20,
        "attributes": {"tonnage": 180},
    },
    {
        "kind": "machine",
        "code": "IM-220T",
        "name_en": "Injection machine 220T",
        "name_zh_tw": "220 噸射出機",
        "sort_order": 30,
        "attributes": {"tonnage": 220},
    },
    {
        "kind": "defect",
        "code": "short_shot",
        "name_en": "Short shot",
        "name_zh_tw": "短射",
        "sort_order": 10,
        "attributes": {"default_severity": "major", "inspection_method": "visual"},
    },
    {
        "kind": "defect",
        "code": "sink_mark",
        "name_en": "Sink mark",
        "name_zh_tw": "縮痕",
        "sort_order": 20,
        "attributes": {"default_severity": "major", "inspection_method": "visual"},
    },
    {
        "kind": "defect",
        "code": "warpage",
        "name_en": "Warpage",
        "name_zh_tw": "翹曲",
        "sort_order": 30,
        "attributes": {"default_severity": "major", "inspection_method": "fixture"},
    },
    {
        "kind": "defect",
        "code": "flash",
        "name_en": "Flash",
        "name_zh_tw": "毛邊",
        "sort_order": 40,
        "attributes": {"default_severity": "minor", "inspection_method": "visual"},
    },
    {
        "kind": "location",
        "code": "far_flow_end",
        "name_en": "Far flow end",
        "name_zh_tw": "流動末端",
        "sort_order": 10,
    },
    {
        "kind": "location",
        "code": "gate_area",
        "name_en": "Gate area",
        "name_zh_tw": "澆口區",
        "sort_order": 20,
    },
    {
        "kind": "location",
        "code": "core_side",
        "name_en": "Core side",
        "name_zh_tw": "公模側",
        "sort_order": 30,
    },
    {
        "kind": "location",
        "code": "cavity_side",
        "name_en": "Cavity side",
        "name_zh_tw": "母模側",
        "sort_order": 40,
    },
    {
        "kind": "location",
        "code": "parting_line",
        "name_en": "Parting line",
        "name_zh_tw": "分模線",
        "sort_order": 50,
    },
    {
        "kind": "unit",
        "code": "mm",
        "name_en": "Millimetre",
        "name_zh_tw": "毫米",
        "sort_order": 10,
        "attributes": {"dimension": "length", "symbol": "mm"},
    },
    {
        "kind": "unit",
        "code": "MPa",
        "name_en": "Megapascal",
        "name_zh_tw": "百萬帕",
        "sort_order": 20,
        "attributes": {"dimension": "pressure", "symbol": "MPa"},
    },
    {
        "kind": "unit",
        "code": "degC",
        "name_en": "Degree Celsius",
        "name_zh_tw": "攝氏度",
        "sort_order": 30,
        "attributes": {"dimension": "temperature", "symbol": "°C"},
    },
    {
        "kind": "unit",
        "code": "s",
        "name_en": "Second",
        "name_zh_tw": "秒",
        "sort_order": 40,
        "attributes": {"dimension": "time", "symbol": "s"},
    },
    {
        "kind": "mold_type",
        "code": "injection",
        "name_en": "General injection mold",
        "name_zh_tw": "一般射出模具",
        "sort_order": 10,
        "attributes": {"process_family": "injection"},
    },
    {
        "kind": "mold_type",
        "code": "two_plate",
        "name_en": "Two-plate mold",
        "name_zh_tw": "二板模",
        "sort_order": 20,
        "attributes": {"process_family": "injection", "plate_count": 2},
    },
    {
        "kind": "mold_type",
        "code": "three_plate",
        "name_en": "Three-plate mold",
        "name_zh_tw": "三板模",
        "sort_order": 30,
        "attributes": {"process_family": "injection", "plate_count": 3},
    },
    {
        "kind": "mold_type",
        "code": "hot_runner",
        "name_en": "Hot-runner mold",
        "name_zh_tw": "熱澆道模具",
        "sort_order": 40,
        "attributes": {"process_family": "injection", "hot_runner": True},
    },
    {
        "kind": "mold_type",
        "code": "insert_overmolding",
        "name_en": "Insert / overmolding mold",
        "name_zh_tw": "埋入／包覆成型模具",
        "sort_order": 50,
        "attributes": {"process_family": "overmolding"},
    },
    {
        "kind": "mold_type",
        "code": "unscrewing",
        "name_en": "Unscrewing mold",
        "name_zh_tw": "旋牙／退牙模具",
        "sort_order": 60,
        "attributes": {"process_family": "injection", "unscrewing": True},
    },
    {
        "kind": "mold_type",
        "code": "multi_cavity",
        "name_en": "Multi-cavity mold",
        "name_zh_tw": "多穴模具",
        "sort_order": 70,
        "attributes": {"process_family": "injection", "multi_cavity": True},
    },
    {
        "kind": "mold_type",
        "code": "family_mold",
        "name_en": "Family mold",
        "name_zh_tw": "共模／Family Mold",
        "sort_order": 80,
        "attributes": {"process_family": "injection", "family_mold": True},
    },
    {
        "kind": "molding_process",
        "code": "injection",
        "name_en": "Injection molding",
        "name_zh_tw": "射出成型",
        "sort_order": 10,
    },
    {
        "kind": "molding_process",
        "code": "compression",
        "name_en": "Compression molding",
        "name_zh_tw": "壓縮成型",
        "sort_order": 20,
    },
    {
        "kind": "molding_process",
        "code": "overmolding",
        "name_en": "Insert / overmolding",
        "name_zh_tw": "埋入／包覆成型",
        "sort_order": 30,
    },
    {
        "kind": "rule_category",
        "code": "mold_design",
        "name_en": "Mold design",
        "name_zh_tw": "模具設計",
        "sort_order": 10,
    },
    {
        "kind": "rule_category",
        "code": "product_design",
        "name_en": "Product design",
        "name_zh_tw": "產品設計",
        "sort_order": 20,
    },
    {
        "kind": "rule_category",
        "code": "material",
        "name_en": "Material",
        "name_zh_tw": "材料",
        "sort_order": 30,
    },
    {
        "kind": "rule_category",
        "code": "process",
        "name_en": "Process",
        "name_zh_tw": "製程",
        "sort_order": 40,
    },
    {
        "kind": "rule_category",
        "code": "quality",
        "name_en": "Quality",
        "name_zh_tw": "品質",
        "sort_order": 50,
    },
)


def invalidate_master_data_cache() -> None:
    cache.delete(MASTER_DATA_CACHE_KEY)


def seed_master_data(*, actor_id: str = "system:seed", dry_run: bool = False) -> tuple[int, int]:
    scope = DataScope.objects.get(code="public-demo")
    created = updated = 0
    for seed in MASTER_DATA_SEED:
        lookup = {"scope": scope, "kind": seed["kind"], "code": seed["code"]}
        defaults = {
            "name_en": seed["name_en"],
            "name_zh_tw": seed["name_zh_tw"],
            "sort_order": seed.get("sort_order", 100),
            "attributes": seed.get("attributes", {}),
            "source_system": "public_demo_seed",
            "source_refs": ["phase-2:canonical-master-data"],
            "classification": "public_demo",
            "created_by": actor_id,
            "updated_by": actor_id,
        }
        item = MasterDataItem.objects.filter(**lookup).first()
        if item is None:
            created += 1
            if not dry_run:
                MasterDataItem.objects.create(**lookup, **defaults)
        # Existing rows are intentionally left untouched: a restart must never
        # overwrite changes made by a data steward in the governed UI.
    if not dry_run:
        invalidate_master_data_cache()
    return created, updated


def reference_summary(item: MasterDataItem) -> dict[str, int]:
    refs: Counter[str] = Counter()
    if item.kind == MasterDataItem.Kind.DATASET:
        refs["artifacts"] = Artifact.objects.filter(dataset_id=item.code).count()
    elif item.kind == MasterDataItem.Kind.PRODUCT_TYPE:
        refs["artifacts"] = Artifact.objects.filter(product_type=item.code).count()
        refs["trial_cases"] = TrialCase.objects.filter(product_type=item.code).count()
    elif item.kind == MasterDataItem.Kind.MATERIAL:
        refs["artifacts"] = Artifact.objects.filter(material_code=item.code).count()
        refs["trial_cases"] = TrialCase.objects.filter(material_code=item.code).count()
    elif item.kind == MasterDataItem.Kind.MACHINE:
        refs["trial_cases"] = TrialCase.objects.filter(machine_code=item.code).count()
    elif item.kind == MasterDataItem.Kind.DEFECT:
        refs["defect_observations"] = DefectObservation.objects.filter(
            defect_code=item.code
        ).count()
    elif item.kind == MasterDataItem.Kind.LOCATION:
        refs["defect_observations"] = DefectObservation.objects.filter(location=item.code).count()
    elif item.kind == MasterDataItem.Kind.UNIT:
        refs["process_parameters"] = ProcessParameter.objects.filter(unit=item.code).count()
    elif item.kind == MasterDataItem.Kind.MOLD_TYPE:
        refs["molds"] = Mold.objects.filter(mold_type=item.code).count()
    return {key: value for key, value in refs.items() if value}


def master_data_payload(
    item: MasterDataItem, *, include_references: bool = False
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(item.id),
        "kind": item.kind,
        "code": item.code,
        "name_en": item.name_en,
        "name_zh_tw": item.name_zh_tw,
        "description_en": item.description_en,
        "description_zh_tw": item.description_zh_tw,
        "status": item.status,
        "sort_order": item.sort_order,
        "attributes": item.attributes,
        "aliases": item.aliases,
        "source_system": item.source_system,
        "source_refs": item.source_refs,
        "scope": item.scope.code,
        "classification": item.classification,
        "effective_from": item.effective_from.isoformat() if item.effective_from else None,
        "effective_to": item.effective_to.isoformat() if item.effective_to else None,
        "row_version": item.row_version,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }
    if include_references:
        payload["references"] = reference_summary(item)
    return payload


def master_data_etag(item: MasterDataItem) -> str:
    return f'W/"master-data-{item.id}-{item.row_version}"'


def active_options_payload() -> dict[str, list[dict[str, Any]]]:
    cached = cache.get(MASTER_DATA_CACHE_KEY)
    if isinstance(cached, dict):
        return cached
    grouped: dict[str, list[dict[str, Any]]] = {kind: [] for kind in sorted(MASTER_DATA_KINDS)}
    for item in MasterDataItem.objects.select_related("scope").filter(
        status=MasterDataItem.Status.ACTIVE
    ):
        grouped[item.kind].append(
            {
                "id": str(item.id),
                "code": item.code,
                "name_en": item.name_en,
                "name_zh_tw": item.name_zh_tw,
                "attributes": item.attributes,
                "row_version": item.row_version,
            }
        )
    cache.set(MASTER_DATA_CACHE_KEY, grouped, timeout=60)
    return grouped
