import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from platform_core.models import Artifact, ArtifactVersion, CADModel


class CADIndexMigrationCommandTests(TestCase):
    def setUp(self) -> None:
        artifact = Artifact.objects.create(name="cad", kind=Artifact.Kind.CAD_SOURCE)
        version = ArtifactVersion.objects.create(
            artifact=artifact,
            version_number=1,
            original_filename="cad.stl",
            media_type="model/stl",
            format="stl",
            size_bytes=1,
            sha256="a" * 64,
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
            sha256="b" * 64,
            storage_key="preview.stl",
        )
        self.model = CADModel.objects.create(
            artifact_version=version,
            preview_artifact_version=preview,
            geometry_status=CADModel.GeometryStatus.SUCCEEDED,
        )

    def test_validate_is_read_only_and_reports_missing(self) -> None:
        output = StringIO()
        call_command("migrate_cad_index_v2", stdout=output)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["missing"], 1)
        self.assertEqual(payload["indexed"], 0)
        self.assertFalse(payload["activation_changed"])

    @patch("platform_core.management.commands.migrate_cad_index_v2.extract_and_index_cad_model_v2")
    def test_apply_calls_idempotent_v2_pipeline(self, extract) -> None:
        output = StringIO()
        call_command("migrate_cad_index_v2", "--apply", stdout=output)
        self.assertEqual(json.loads(output.getvalue())["indexed"], 1)
        extract.assert_called_once_with(self.model)
