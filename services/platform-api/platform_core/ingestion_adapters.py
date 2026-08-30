from __future__ import annotations

from dataclasses import dataclass

from .models import (
    BulkImportBatch,
    MasterDataItem,
    Mold,
    MoldRevision,
    ProductPart,
    Project,
    RuleProfile,
    RuleProfileApplicability,
    RuleVersion,
)

MAX_BATCH_RECORDS = 10_000
SUPPORTED_INGESTION_DOMAINS = {"master_data", "projects", "registry", "rule_profiles"}
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

    raise ValueError(f"No commit adapter for {batch.domain}.")
