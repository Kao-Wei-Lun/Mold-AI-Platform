import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from platform_core.models import Artifact, ArtifactVersion, KnowledgeChunk, KnowledgeDocument


class KnowledgeIndexMigrationCommandTests(TestCase):
    def setUp(self) -> None:
        artifact = Artifact.objects.create(
            name="guide", kind=Artifact.Kind.KNOWLEDGE_SOURCE, dataset_id="public-knowledge-demo-v1"
        )
        version = ArtifactVersion.objects.create(
            artifact=artifact,
            version_number=1,
            original_filename="guide.md",
            media_type="text/markdown",
            format="markdown",
            size_bytes=10,
            sha256="c" * 64,
            storage_key="knowledge/guide.md",
        )
        self.document = KnowledgeDocument.objects.create(
            artifact_version=version,
            document_type="design_guideline",
            authority_level="reviewed_demo",
            owner="test",
            ingestion_status=KnowledgeDocument.IngestionStatus.INDEXED,
            publication_status="published",
        )
        self.chunk = KnowledgeChunk.objects.create(
            document=self.document,
            ordinal=1,
            text="Nominal wall thickness guidance.",
            text_hash="d" * 64,
            embedding_dimension=64,
            index_status=KnowledgeChunk.IndexStatus.INDEXED,
        )

    def test_validate_reports_missing_without_writes(self) -> None:
        output = StringIO()
        call_command("migrate_knowledge_index_v2", stdout=output)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["missing_chunks"], 1)
        self.assertEqual(payload["indexed_documents"], 0)
        self.assertFalse(payload["activation_changed"])

    @patch("platform_core.knowledge.upsert_hybrid_point")
    def test_apply_populates_v2_without_replacing_canonical_chunk(self, upsert) -> None:
        original_id = self.chunk.id
        output = StringIO()
        call_command("migrate_knowledge_index_v2", "--apply", stdout=output)
        self.chunk.refresh_from_db()
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["missing_chunks"], 0)
        self.assertEqual(self.chunk.id, original_id)
        self.assertTrue(self.chunk.embedding_v2_model)
        self.assertIsNotNone(self.chunk.embedding_v2_dimension)
        upsert.assert_called_once()
