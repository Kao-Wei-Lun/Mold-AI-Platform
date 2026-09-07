import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from platform_core.models import (
    Artifact,
    ArtifactVersion,
    CADModel,
    FeatureSet,
    KnowledgeChunk,
    KnowledgeDocument,
)


class CPUAIReleaseGateTests(TestCase):
    def setUp(self) -> None:
        cad_artifact = Artifact.objects.create(name="cad", kind=Artifact.Kind.CAD_SOURCE)
        cad_version = ArtifactVersion.objects.create(
            artifact=cad_artifact,
            version_number=1,
            original_filename="cad.stl",
            media_type="model/stl",
            format="stl",
            size_bytes=1,
            sha256="1" * 64,
            storage_key="cad.stl",
        )
        preview_artifact = Artifact.objects.create(name="preview", kind=Artifact.Kind.CAD_PREVIEW)
        preview = ArtifactVersion.objects.create(
            artifact=preview_artifact,
            version_number=1,
            original_filename="preview.stl",
            media_type="model/stl",
            format="stl",
            size_bytes=1,
            sha256="2" * 64,
            storage_key="preview.stl",
        )
        cad_model = CADModel.objects.create(
            artifact_version=cad_version,
            preview_artifact_version=preview,
            geometry_status=CADModel.GeometryStatus.SUCCEEDED,
        )
        for schema, extractor, dimension, index_version in (
            ("1.0", "1.0.0", 12, "cad-demo-v1"),
            ("2.0", "2.1.0", 32, "cad-cpu-v2"),
        ):
            FeatureSet.objects.create(
                cad_model=cad_model,
                schema_version=schema,
                extractor_version=extractor,
                vector=[0.1] * dimension,
                vector_dimension=dimension,
                vector_checksum="3" * 64,
                index_collection=f"cad-{schema}",
                index_version=index_version,
                index_status=FeatureSet.IndexStatus.INDEXED,
            )
        knowledge_artifact = Artifact.objects.create(
            name="guide", kind=Artifact.Kind.KNOWLEDGE_SOURCE
        )
        knowledge_version = ArtifactVersion.objects.create(
            artifact=knowledge_artifact,
            version_number=1,
            original_filename="guide.md",
            media_type="text/markdown",
            format="markdown",
            size_bytes=1,
            sha256="4" * 64,
            storage_key="guide.md",
        )
        document = KnowledgeDocument.objects.create(
            artifact_version=knowledge_version,
            document_type="design_guideline",
            owner="test",
            ingestion_status=KnowledgeDocument.IngestionStatus.INDEXED,
            publication_status="published",
        )
        KnowledgeChunk.objects.create(
            document=document,
            ordinal=1,
            text="guide",
            text_hash="5" * 64,
            embedding=[0.1] * 64,
            embedding_dimension=64,
            embedding_v2_model="fastembed",
            embedding_v2_dimension=512,
            embedding_v2_checksum="6" * 64,
            sparse_encoder="hashing",
            index_status=KnowledgeChunk.IndexStatus.INDEXED,
        )

    def test_structural_gate_passes_without_qdrant(self) -> None:
        output = StringIO()
        call_command("cpu_ai_release_gate", "--skip-qdrant", stdout=output)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["passed"])
        self.assertFalse(payload["environment"]["gpu_required"])
        self.assertEqual(payload["quality_gate"]["status"], "domain_approval_required")

    @patch("platform_core.management.commands.cpu_ai_release_gate.replace_collection_alias")
    @patch("platform_core.management.commands.cpu_ai_release_gate.create_collection_snapshot")
    @patch("platform_core.management.commands.cpu_ai_release_gate.exact_point_count")
    @patch("platform_core.management.commands.cpu_ai_release_gate.collection_info")
    def test_alias_snapshot_and_rollback_drill_are_exercised(
        self, info, point_count, snapshot, replace_alias
    ) -> None:
        point_count.return_value = 10
        snapshot.return_value = {"name": "snapshot"}
        output = StringIO()
        call_command(
            "cpu_ai_release_gate",
            "--prepare-aliases",
            "--snapshot",
            "--rollback-drill",
            stdout=output,
        )
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["passed"])
        self.assertEqual(info.call_count, 4)
        self.assertEqual(snapshot.call_count, 4)
        self.assertEqual(replace_alias.call_count, 6)
        self.assertEqual(len(payload["aliases"]), 6)
