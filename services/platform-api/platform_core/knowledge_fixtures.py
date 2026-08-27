from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile

from .knowledge import (
    AUTOMATED_SMOKE_DATASET,
    PUBLIC_KNOWLEDGE_DATASET,
    create_knowledge_upload_records,
)
from .models import Artifact, Job, KnowledgeDocument

DEMO_DATA_DIRECTORY = Path(__file__).with_name("demo_data")
FIXTURE_VERSION = "2026.08.1"
FIXTURES: tuple[dict[str, str], ...] = (
    {
        "filename": "short_shot_troubleshooting_zh_hant.md",
        "title": "射出成型短射 Demo 排查指南",
        "document_type": "design_guideline",
        "authority_level": "reviewed_demo",
        "language": "zh-Hant",
    },
)


@dataclass(frozen=True)
class KnowledgeSeedResult:
    fixture_version: str
    created: int
    existing: int
    indexed: int
    relabeled_smoke_documents: int
    document_ids: list[str]


def seed_demo_knowledge() -> KnowledgeSeedResult:
    relabeled = Artifact.objects.filter(
        kind=Artifact.Kind.KNOWLEDGE_SOURCE,
        name="Stage 5 smoke knowledge guide",
        dataset_id=PUBLIC_KNOWLEDGE_DATASET,
    ).update(dataset_id=AUTOMATED_SMOKE_DATASET)
    created = 0
    existing = 0
    indexed = 0
    document_ids: list[str] = []

    for fixture in FIXTURES:
        content = (DEMO_DATA_DIRECTORY / fixture["filename"]).read_bytes()
        upload = SimpleUploadedFile(fixture["filename"], content, content_type="text/markdown")
        records = create_knowledge_upload_records(
            upload,
            title=fixture["title"],
            document_type=fixture["document_type"],
            authority_level=fixture["authority_level"],
            owner="mold-ai-demo-curator",
            language=fixture["language"],
            effective_from=None,
            effective_to=None,
            idempotency_key=f"demo-knowledge-{fixture['filename']}-{FIXTURE_VERSION}",
            dataset_id=PUBLIC_KNOWLEDGE_DATASET,
        )
        if records.created:
            from .tasks import process_knowledge_job

            outcome = process_knowledge_job.run(str(records.job.id))
            if outcome["state"] != Job.State.SUCCEEDED:
                raise RuntimeError(f"Demo knowledge fixture failed to index: {fixture['filename']}")
            created += 1
        else:
            existing += 1
        records.document.refresh_from_db()
        if records.document.ingestion_status != KnowledgeDocument.IngestionStatus.INDEXED:
            raise RuntimeError(
                "Demo knowledge fixture is not indexed: "
                f"{fixture['filename']} ({records.document.ingestion_status})"
            )
        indexed += 1
        document_ids.append(str(records.document.id))

    return KnowledgeSeedResult(
        fixture_version=FIXTURE_VERSION,
        created=created,
        existing=existing,
        indexed=indexed,
        relabeled_smoke_documents=relabeled,
        document_ids=document_ids,
    )
