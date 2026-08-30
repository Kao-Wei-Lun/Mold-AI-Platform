from __future__ import annotations

from dataclasses import dataclass

from .models import (
    BulkImportBatch,
    MasterDataItem,
    Mold,
    MoldRevision,
    ProductPart,
    Project,
)

MAX_BATCH_RECORDS = 10_000
SUPPORTED_INGESTION_DOMAINS = {"master_data", "projects", "registry"}


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

    raise ValueError(f"No commit adapter for {batch.domain}.")
