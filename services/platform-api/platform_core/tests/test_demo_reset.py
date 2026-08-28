from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from platform_core.demo_reset import DemoResetError, reset_demo_operations
from platform_core.ingestion import create_upload_records
from platform_core.models import (
    Artifact,
    ArtifactVersion,
    AuditEvent,
    CADModel,
    KnowledgeSearch,
)


class DemoOperationsResetTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    def _manual_upload(self):
        return create_upload_records(
            SimpleUploadedFile(
                "manual.stl",
                b"solid manual\nfacet normal 0 0 1\nendsolid manual\n",
                content_type="model/stl",
            ),
            dataset_id="manual-cad-upload-v1",
        )

    def test_dry_run_is_read_only_and_reports_scope(self) -> None:
        upload = self._manual_upload()
        KnowledgeSearch.objects.create(query="temporary", result={})

        result = reset_demo_operations()

        self.assertTrue(result.dry_run)
        self.assertEqual(result.counts["artifacts"], 1)
        self.assertTrue(Artifact.objects.filter(pk=upload.artifact.id).exists())
        self.assertEqual(KnowledgeSearch.objects.count(), 1)

    def test_wrong_confirmation_fails_without_changes(self) -> None:
        upload = self._manual_upload()
        with self.assertRaises(DemoResetError):
            reset_demo_operations(confirmation="yes", dry_run=False)
        self.assertTrue(Artifact.objects.filter(pk=upload.artifact.id).exists())

    @patch("platform_core.demo_reset.delete_feature_points")
    def test_confirmed_reset_removes_operations_and_preserves_audit_history(self, delete_points):
        upload = self._manual_upload()
        curated = Artifact.objects.create(
            name="Curated fixture",
            kind=Artifact.Kind.CAD_SOURCE,
            dataset_id="curated-cad-demo-v1",
            classification="public_demo",
        )
        curated_version = ArtifactVersion.objects.create(
            artifact=curated,
            original_filename="curated.stl",
            media_type="model/stl",
            format="stl",
            size_bytes=1,
            sha256="b" * 64,
            storage_key="curated/source.stl",
            source_system="curated-cad-generator",
            classification="public_demo",
        )
        preview_artifact = Artifact.objects.create(
            name="Curated preview",
            kind=Artifact.Kind.CAD_PREVIEW,
            dataset_id="public-demo-v1",
            classification="public_demo",
        )
        preview_version = ArtifactVersion.objects.create(
            artifact=preview_artifact,
            original_filename="curated.preview.stl",
            media_type="model/stl",
            format="stl",
            size_bytes=1,
            sha256="c" * 64,
            storage_key="curated/preview.stl",
            source_system="cad-worker",
            classification="public_demo",
        )
        CADModel.objects.create(
            artifact_version=curated_version,
            cad_format="stl",
            preview_artifact_version=preview_version,
        )
        AuditEvent.objects.create(
            event_type="existing.audit",
            actor_id="tester",
            target_refs=[],
            detail={},
            payload_hash="a" * 64,
        )
        KnowledgeSearch.objects.create(query="temporary", result={})

        result = reset_demo_operations(confirmation="RESET OPERATIONS", dry_run=False)

        self.assertFalse(result.dry_run)
        self.assertFalse(Artifact.objects.filter(pk=upload.artifact.id).exists())
        self.assertTrue(Artifact.objects.filter(pk=curated.id).exists())
        self.assertTrue(Artifact.objects.filter(pk=preview_artifact.id).exists())
        self.assertEqual(KnowledgeSearch.objects.count(), 0)
        self.assertTrue(AuditEvent.objects.filter(event_type="existing.audit").exists())
        self.assertTrue(AuditEvent.objects.filter(event_type="demo.operations_reset.v1").exists())
        delete_points.assert_called_once_with([])
