from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    BulkImportBatch,
    CAEResult,
    CAERun,
    CAEStudy,
    MasterDataItem,
    Mold,
    MoldRevision,
    ProcessParameter,
    ProcessRun,
    ProductPart,
    Project,
    RuleProfile,
    RuleProfileApplicability,
    RuleVersion,
    TrialCase,
)

MAX_BATCH_RECORDS = 10_000
SUPPORTED_INGESTION_DOMAINS = {
    "master_data",
    "projects",
    "registry",
    "rule_profiles",
    "trials",
    "cae_results",
}
RULE_EVALUATORS = {
    "bbox_dimension",
    "bbox_aspect_ratio",
    "cad_scalar",
    "edge_face_ratio",
    "quality_flag_absent",
    "unit_known",
    "surface_share",
    "context_ratio",
    "context_value",
}


@dataclass(frozen=True)
class CommitResult:
    entity_type: str
    entity_id: str
    created: bool


def _mapped(record: object, mapping: dict[str, str]) -> dict[str, object]:
    if not isinstance(record, dict):
        return {}
    return {
        canonical: record.get(source)
        for canonical, source in mapping.items()
        if isinstance(canonical, str) and isinstance(source, str)
    } | {key: value for key, value in record.items() if key not in mapping.values()}


def _active_reference(scope, kind: str, code: object) -> bool:
    value = str(code or "").strip()
    return (
        not value
        or MasterDataItem.objects.filter(
            scope=scope,
            kind=kind,
            code__iexact=value,
            status=MasterDataItem.Status.ACTIVE,
        ).exists()
    )


def _issue(row: int, code: str, *, field: str = "", value: object = None) -> dict:
    messages = {
        "REQUIRED_FIELDS": "Required canonical fields are missing.",
        "INVALID_KIND": "The engineering reference type is not governed.",
        "DUPLICATE_IN_BATCH": "The canonical identity is duplicated in this batch.",
        "REFERENCE_NOT_FOUND": "The referenced engineering code is not active in this scope.",
        "INVALID_POSITIVE_INTEGER": "The value must be a positive integer.",
        "INVALID_RULE": "The rule evaluator, operator, or numeric condition is invalid.",
        "PROFILE_SCOPE_CONFLICT": "This profile identity already belongs to another data scope.",
        "INVALID_DATETIME": "The timestamp must be an ISO 8601 date and time.",
        "INVALID_PROCESS_PARAMETER": "Run number, value, or value kind is invalid.",
        "IMMUTABLE_TRIAL": "Existing closed trial evidence cannot be changed by import.",
        "INVALID_CAE_RESULT": (
            "The CAE status, result type, numeric value, or JSON settings are invalid."
        ),
    }
    return {
        "row": row,
        "field": field,
        "code": code,
        "message": messages[code],
        "value": value,
    }


def validate_records(
    domain: str,
    records: list[object],
    mapping: dict[str, str],
    scope,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    normalized = [_mapped(record, mapping) for record in records]
    issues: list[dict[str, object]] = []
    seen: set[tuple[str, ...]] = set()
    existing = 0
    valid_kinds = {item.value for item in MasterDataItem.Kind}

    for index, record in enumerate(normalized, start=1):
        if domain == "master_data":
            required = ("kind", "code", "name_en")
            identity = (str(record.get("kind", "")).lower(), str(record.get("code", "")).lower())
            if record.get("kind") not in valid_kinds:
                issues.append(_issue(index, "INVALID_KIND", field="kind", value=record.get("kind")))
            existing += int(
                MasterDataItem.objects.filter(
                    scope=scope,
                    kind=record.get("kind", ""),
                    code__iexact=record.get("code", ""),
                ).exists()
            )
        elif domain == "projects":
            required = ("code", "name")
            identity = (str(record.get("code", "")).lower(),)
            existing += int(
                Project.objects.filter(scope=scope, code__iexact=record.get("code", "")).exists()
            )
        elif domain == "registry":
            required = ("project_code", "project_name", "mold_code", "mold_name", "revision_code")
            identity = (
                str(record.get("project_code", "")).lower(),
                str(record.get("mold_code", "")).lower(),
                str(record.get("revision_code", "")).lower(),
            )
            for field, kind in (
                ("mold_type", MasterDataItem.Kind.MOLD_TYPE),
                ("product_type", MasterDataItem.Kind.PRODUCT_TYPE),
                ("material_code", MasterDataItem.Kind.MATERIAL),
            ):
                if not _active_reference(scope, kind, record.get(field)):
                    issues.append(
                        _issue(index, "REFERENCE_NOT_FOUND", field=field, value=record.get(field))
                    )
            try:
                cavity_count = int(record.get("cavity_count") or 1)
                if cavity_count < 1:
                    raise ValueError
                record["cavity_count"] = cavity_count
            except (TypeError, ValueError):
                issues.append(
                    _issue(
                        index,
                        "INVALID_POSITIVE_INTEGER",
                        field="cavity_count",
                        value=record.get("cavity_count"),
                    )
                )
            existing_mold = Mold.objects.filter(
                project__scope=scope,
                project__code__iexact=record.get("project_code", ""),
                mold_code__iexact=record.get("mold_code", ""),
            ).first()
            if existing_mold:
                existing += int(
                    MoldRevision.objects.filter(
                        mold=existing_mold,
                        revision_code__iexact=record.get("revision_code", ""),
                    ).exists()
                )
        elif domain == "rule_profiles":
            required = (
                "profile_key",
                "version",
                "rule_id",
                "title",
                "evaluator",
                "operator",
                "severity",
            )
            identity = (
                str(record.get("profile_key", "")).lower(),
                str(record.get("version", "")).lower(),
                str(record.get("rule_id", "")).lower(),
            )
            invalid_condition = str(record.get("evaluator", "")) not in RULE_EVALUATORS or str(
                record.get("operator", "")
            ) not in {"lte", "gte", "eq"}
            for field in ("limit_value", "tolerance"):
                try:
                    record[field] = float(record.get(field) or 0)
                except (TypeError, ValueError):
                    invalid_condition = True
            if invalid_condition:
                issues.append(_issue(index, "INVALID_RULE", field="condition"))
            cross_scope = RuleProfile.objects.filter(
                profile_key__iexact=record.get("profile_key", ""),
                version=record.get("version", ""),
            ).exclude(scope=scope)
            if cross_scope.exists():
                issues.append(_issue(index, "PROFILE_SCOPE_CONFLICT", field="profile_key"))
            profile = RuleProfile.objects.filter(
                scope=scope,
                profile_key__iexact=record.get("profile_key", ""),
                version=record.get("version", ""),
            ).first()
            if profile:
                existing += int(
                    RuleVersion.objects.filter(
                        profile=profile,
                        rule_id__iexact=record.get("rule_id", ""),
                        rule_version=record.get("version", ""),
                    ).exists()
                )
                if profile.workflow_status != RuleProfile.WorkflowStatus.DRAFT:
                    issues.append(_issue(index, "INVALID_RULE", field="workflow_status"))
            for field, kind in (
                ("mold_type", MasterDataItem.Kind.MOLD_TYPE),
                ("product_type", MasterDataItem.Kind.PRODUCT_TYPE),
                ("material", MasterDataItem.Kind.MATERIAL),
                ("molding_process", MasterDataItem.Kind.MOLDING_PROCESS),
            ):
                if not _active_reference(scope, kind, record.get(field)):
                    issues.append(
                        _issue(index, "REFERENCE_NOT_FOUND", field=field, value=record.get(field))
                    )
        elif domain == "trials":
            required = (
                "case_code",
                "mold_revision_ref",
                "machine_code",
                "material_code",
                "product_type",
                "purpose",
                "started_at",
                "run_number",
                "result",
                "parameter_code",
                "parameter_value",
                "parameter_unit",
                "value_kind",
            )
            identity = (
                str(record.get("case_code", "")).lower(),
                str(record.get("run_number", "")),
                str(record.get("parameter_code", "")).lower(),
                str(record.get("value_kind", "")).lower(),
            )
            parsed = parse_datetime(str(record.get("started_at", "")))
            if parsed is None:
                issues.append(_issue(index, "INVALID_DATETIME", field="started_at"))
            else:
                record["started_at"] = parsed.isoformat()
            try:
                record["run_number"] = int(record.get("run_number"))
                record["parameter_value"] = float(record.get("parameter_value"))
                if (
                    record["run_number"] < 1
                    or record.get("value_kind") not in ProcessParameter.ValueKind.values
                ):
                    raise ValueError
            except (TypeError, ValueError):
                issues.append(_issue(index, "INVALID_PROCESS_PARAMETER", field="parameter_value"))
            for field, kind in (
                ("machine_code", MasterDataItem.Kind.MACHINE),
                ("material_code", MasterDataItem.Kind.MATERIAL),
                ("product_type", MasterDataItem.Kind.PRODUCT_TYPE),
                ("parameter_unit", MasterDataItem.Kind.UNIT),
            ):
                if not _active_reference(scope, kind, record.get(field)):
                    issues.append(
                        _issue(index, "REFERENCE_NOT_FOUND", field=field, value=record.get(field))
                    )
            trial = TrialCase.objects.filter(case_code__iexact=record.get("case_code", "")).first()
            if trial:
                if scope.code not in trial.acl_scopes:
                    issues.append(_issue(index, "PROFILE_SCOPE_CONFLICT", field="case_code"))
                elif trial.lifecycle_status != TrialCase.LifecycleStatus.DRAFT:
                    issues.append(_issue(index, "IMMUTABLE_TRIAL", field="case_code"))
                else:
                    run = ProcessRun.objects.filter(
                        trial=trial, run_number=record.get("run_number")
                    ).first()
                    if run:
                        existing += int(
                            ProcessParameter.objects.filter(
                                process_run=run,
                                canonical_code__iexact=record.get("parameter_code", ""),
                                value_kind=record.get("value_kind", ""),
                            ).exists()
                        )
        elif domain == "cae_results":
            required = (
                "study_code",
                "solver_name",
                "product_ref",
                "mold_revision_ref",
                "material_model_code",
                "mesh_family",
                "objective",
                "run_code",
                "solver_version",
                "unit_system",
                "status",
                "metric_code",
                "result_type",
                "value",
                "unit",
            )
            identity = (
                str(record.get("study_code", "")).lower(),
                str(record.get("run_code", "")).lower(),
                str(record.get("metric_code", "")).lower(),
            )
            invalid_cae = (
                record.get("status") not in CAERun.Status.values
                or record.get("result_type") not in CAEResult.ResultType.values
            )
            try:
                record["value"] = float(record.get("value"))
                for field in ("boundary_settings", "process_settings", "location", "field_summary"):
                    value = record.get(field) or {}
                    if isinstance(value, str):
                        value = json.loads(value)
                    if not isinstance(value, dict):
                        raise ValueError
                    record[field] = value
            except (TypeError, ValueError, json.JSONDecodeError):
                invalid_cae = True
            if invalid_cae:
                issues.append(_issue(index, "INVALID_CAE_RESULT", field="value"))
            if not _active_reference(scope, MasterDataItem.Kind.UNIT, record.get("unit")):
                issues.append(
                    _issue(index, "REFERENCE_NOT_FOUND", field="unit", value=record.get("unit"))
                )
            study = CAEStudy.objects.filter(study_code__iexact=record.get("study_code", "")).first()
            if study:
                if scope.code not in study.acl_scopes:
                    issues.append(_issue(index, "PROFILE_SCOPE_CONFLICT", field="study_code"))
                else:
                    run = CAERun.objects.filter(
                        study=study, run_code=record.get("run_code", "")
                    ).first()
                    if run:
                        existing += int(
                            CAEResult.objects.filter(
                                run=run, metric_code__iexact=record.get("metric_code", "")
                            ).exists()
                        )
        else:
            raise ValueError(f"Unsupported ingestion domain: {domain}")

        missing = [field for field in required if not str(record.get(field, "")).strip()]
        if missing:
            issue = _issue(index, "REQUIRED_FIELDS")
            issue["fields"] = missing
            issues.append(issue)
        if identity in seen:
            issue = _issue(index, "DUPLICATE_IN_BATCH")
            issue["key"] = identity
            issues.append(issue)
        seen.add(identity)

    invalid_rows = {issue["row"] for issue in issues}
    return normalized, {
        "valid": not issues,
        "record_count": len(records),
        "valid_count": len(records) - len(invalid_rows),
        "existing_count": existing,
        "issues": issues,
    }


def commit_record(batch: BulkImportBatch, record: dict[str, object], actor_id: str) -> CommitResult:
    if batch.domain == "master_data":
        entity = MasterDataItem.objects.filter(
            scope=batch.scope, kind=record["kind"], code__iexact=str(record["code"])
        ).first()
        created = entity is None
        if entity is None:
            entity = MasterDataItem.objects.create(
                scope=batch.scope,
                kind=record["kind"],
                code=str(record["code"]),
                name_en=str(record["name_en"]),
                name_zh_tw=str(record.get("name_zh_tw") or record["name_en"]),
                source_system="ingestion",
                source_refs=[f"ingestion:{batch.id}"],
                classification=batch.classification,
                created_by=actor_id,
                updated_by=actor_id,
            )
        return CommitResult("master_data", str(entity.id), created)

    if batch.domain == "projects":
        entity, created = Project.objects.get_or_create(
            scope=batch.scope,
            code=str(record["code"]),
            defaults={
                "name": str(record["name"]),
                "description": str(record.get("description", "")),
                "classification": batch.classification,
                "created_by": actor_id,
                "updated_by": actor_id,
            },
        )
        return CommitResult("project", str(entity.id), created)

    if batch.domain == "registry":
        project, project_created = Project.objects.get_or_create(
            scope=batch.scope,
            code=str(record["project_code"]),
            defaults={
                "name": str(record["project_name"]),
                "description": str(record.get("project_description", "")),
                "classification": batch.classification,
                "created_by": actor_id,
                "updated_by": actor_id,
            },
        )
        part = None
        part_created = False
        if str(record.get("part_number", "")).strip():
            part, part_created = ProductPart.objects.get_or_create(
                project=project,
                part_number=str(record["part_number"]),
                defaults={
                    "name": str(record.get("part_name") or record["part_number"]),
                    "product_type": str(record.get("product_type", "")),
                    "material_code": str(record.get("material_code", "")),
                    "created_by": actor_id,
                    "updated_by": actor_id,
                },
            )
        mold, mold_created = Mold.objects.get_or_create(
            project=project,
            mold_code=str(record["mold_code"]),
            defaults={
                "product_part": part,
                "name": str(record["mold_name"]),
                "mold_type": str(record.get("mold_type") or "injection"),
                "cavity_count": int(record.get("cavity_count") or 1),
                "created_by": actor_id,
                "updated_by": actor_id,
            },
        )
        revision, revision_created = MoldRevision.objects.get_or_create(
            mold=mold,
            revision_code=str(record["revision_code"]),
            defaults={
                "change_summary": str(record.get("change_summary", "")),
                "source_system": "ingestion",
                "source_revision_id": f"ingestion:{batch.id}",
                "created_by": actor_id,
                "updated_by": actor_id,
            },
        )
        return CommitResult(
            "mold_revision",
            str(revision.id),
            project_created or part_created or mold_created or revision_created,
        )

    if batch.domain == "rule_profiles":
        profile, _ = RuleProfile.objects.get_or_create(
            scope=batch.scope,
            profile_key=str(record["profile_key"]),
            version=str(record["version"]),
            defaults={
                "status": "draft",
                "workflow_status": RuleProfile.WorkflowStatus.DRAFT,
                "classification": batch.classification,
                "owner": actor_id,
                "approved_by": "",
                "ruleset_checksum": "",
                "change_summary": str(record.get("change_summary", "Imported draft")),
            },
        )
        if profile.workflow_status != RuleProfile.WorkflowStatus.DRAFT:
            raise ValueError("Imported rules can only target a draft profile.")
        rule, created = RuleVersion.objects.get_or_create(
            profile=profile,
            rule_id=str(record["rule_id"]),
            rule_version=str(record["version"]),
            defaults={
                "title": str(record["title"]),
                "description": str(record.get("description", "")),
                "evaluator": str(record["evaluator"]),
                "applicability": {},
                "parameters": {},
                "operator": str(record["operator"]),
                "limit_value": float(record.get("limit_value") or 0),
                "unit": str(record.get("unit", "")),
                "tolerance": float(record.get("tolerance") or 0),
                "severity": str(record["severity"]),
                "risk_type": str(record.get("risk_type", "general")),
                "recommendation": str(record.get("recommendation", "")),
                "reference": {
                    "document": str(record.get("reference_document", "")),
                    "revision": str(record.get("reference_revision", "")),
                    "ingestion_batch": str(batch.id),
                },
            },
        )
        dimension_fields = {
            "mold_type": "mold_type",
            "product_type": "product_type",
            "material": "material",
            "molding_process": "molding_process",
        }
        for field, dimension in dimension_fields.items():
            value = str(record.get(field, "")).strip()
            if value:
                RuleProfileApplicability.objects.get_or_create(
                    profile=profile,
                    dimension=dimension,
                    value_code=value,
                    match_mode=RuleProfileApplicability.MatchMode.INCLUDE,
                )
        return CommitResult("rule_version", str(rule.id), created)

    if batch.domain == "trials":
        source_file = batch.source_files.select_related("artifact_version").first()
        source_hash = (
            source_file.sha256
            if source_file
            else hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        )
        started_at = parse_datetime(str(record["started_at"]))
        if started_at and timezone.is_naive(started_at):
            started_at = timezone.make_aware(started_at)
        trial, _ = TrialCase.objects.get_or_create(
            case_code=str(record["case_code"]),
            defaults={
                "connector_key": "ingestion",
                "source_record_id": str(record["case_code"]),
                "source_version": batch.mapping_version,
                "source_hash": source_hash,
                "mapping_version": batch.mapping_version,
                "classification": batch.classification,
                "acl_scopes": [batch.scope.code],
                "mold_revision_ref": str(record["mold_revision_ref"]),
                "part_revision_ref": str(record.get("part_revision_ref", "")),
                "machine_code": str(record["machine_code"]),
                "material_code": str(record["material_code"]),
                "material_lot": str(record.get("material_lot", "")),
                "product_type": str(record["product_type"]),
                "operator_ref": str(record.get("operator_ref") or actor_id),
                "purpose": str(record["purpose"]),
                "outcome": str(record.get("outcome", "pending")),
                "started_at": started_at,
                "data_quality": {"source": "ingestion", "batch_id": str(batch.id)},
                "lifecycle_status": TrialCase.LifecycleStatus.DRAFT,
            },
        )
        if trial.lifecycle_status != TrialCase.LifecycleStatus.DRAFT:
            raise ValueError("Imported process data can only target a draft trial.")
        run, _ = ProcessRun.objects.get_or_create(
            trial=trial,
            run_number=int(record["run_number"]),
            defaults={
                "result": str(record["result"]),
                "data_quality": {"source": "ingestion"},
            },
        )
        parameter, created = ProcessParameter.objects.get_or_create(
            process_run=run,
            canonical_code=str(record["parameter_code"]),
            value_kind=str(record["value_kind"]),
            defaults={
                "raw_name": str(record.get("parameter_name") or record["parameter_code"]),
                "value": float(record["parameter_value"]),
                "unit": str(record["parameter_unit"]),
                "sampling_method": str(record.get("sampling_method") or "imported"),
            },
        )
        return CommitResult("process_parameter", str(parameter.id), created)

    if batch.domain == "cae_results":
        source_file = batch.source_files.select_related("artifact_version").first()
        source_hash = (
            source_file.sha256
            if source_file
            else hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        )
        study, _ = CAEStudy.objects.get_or_create(
            study_code=str(record["study_code"]),
            defaults={
                "connector_key": "ingestion",
                "integration_level": "summary",
                "source_record_id": str(record["study_code"]),
                "source_version": batch.mapping_version,
                "source_hash": source_hash,
                "mapping_version": batch.mapping_version,
                "solver_name": str(record["solver_name"]),
                "product_ref": str(record["product_ref"]),
                "mold_revision_ref": str(record["mold_revision_ref"]),
                "material_model_code": str(record["material_model_code"]),
                "mesh_family": str(record["mesh_family"]),
                "objective": str(record["objective"]),
                "owner": actor_id,
                "classification": batch.classification,
                "acl_scopes": [batch.scope.code],
                "data_quality": {"source": "summary_ingestion"},
            },
        )
        run, _ = CAERun.objects.get_or_create(
            study=study,
            run_code=str(record["run_code"]),
            defaults={
                "solver_name": str(record["solver_name"]),
                "solver_version": str(record["solver_version"]),
                "mesh_artifact_ref": str(record.get("mesh_artifact_ref", "")),
                "mesh_checksum": str(record.get("mesh_checksum", "")),
                "material_model_code": str(record["material_model_code"]),
                "boundary_settings": record.get("boundary_settings", {}),
                "process_settings": record.get("process_settings", {}),
                "unit_system": str(record["unit_system"]),
                "status": str(record["status"]),
                "input_hash": str(record.get("input_hash") or source_hash),
                "data_quality": {"source": "summary_ingestion"},
            },
        )
        result, created = CAEResult.objects.get_or_create(
            run=run,
            metric_code=str(record["metric_code"]),
            defaults={
                "result_type": str(record["result_type"]),
                "value": float(record["value"]),
                "unit": str(record["unit"]),
                "location": record.get("location", {}),
                "field_summary": record.get("field_summary", {}),
                "quality_flags": [],
                "parser_name": "ingestion_summary",
                "parser_version": batch.mapping_version,
                "source_locator": {"batch_id": str(batch.id)},
            },
        )
        return CommitResult("cae_result", str(result.id), created)

    raise ValueError(f"No commit adapter for {batch.domain}.")
