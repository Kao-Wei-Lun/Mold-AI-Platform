import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from platform_core.cad_processing import parse_cad_file
from platform_core.ingestion import create_upload_records
from platform_core.models import ArtifactVersion, CADModel, Job, LineageEdge
from platform_core.tasks import process_cad_job

from .fixtures import ASCII_TETRAHEDRON_STL


@override_settings(SIMILARITY_AUTO_INDEX=False)
class CADProcessingTaskTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    def test_stl_job_creates_geometry_preview_and_lineage(self) -> None:
        upload = SimpleUploadedFile("tetra.stl", ASCII_TETRAHEDRON_STL, content_type="model/stl")
        records = create_upload_records(upload)

        task_result = process_cad_job.run(str(records.job.id))

        records.job.refresh_from_db()
        cad_model = CADModel.objects.select_related("preview_artifact_version").get(
            artifact_version=records.version
        )
        self.assertEqual(task_result["state"], "succeeded")
        self.assertEqual(records.job.state, Job.State.SUCCEEDED)
        self.assertEqual(records.job.progress, 100)
        self.assertEqual(cad_model.geometry_status, CADModel.GeometryStatus.SUCCEEDED)
        self.assertEqual(cad_model.face_count, 4)
        self.assertEqual(cad_model.edge_count, 6)
        self.assertEqual(cad_model.bounding_box["size"], {"x": 1.0, "y": 1.0, "z": 1.0})
        self.assertEqual(cad_model.volume, pytest.approx(1 / 6))
        self.assertIn("UNIT_UNCERTAIN", cad_model.quality_flags)
        self.assertIsNotNone(cad_model.preview_artifact_version)
        self.assertTrue(
            Path(self.media_directory.name, cad_model.preview_artifact_version.storage_key).exists()
        )
        self.assertEqual(ArtifactVersion.objects.count(), 2)
        self.assertEqual(LineageEdge.objects.count(), 1)
        self.assertEqual(
            list(records.job.events.values_list("to_state", flat=True)),
            ["queued", "running", "running", "running", "succeeded"],
        )

        status_response = self.client.get(f"/api/v1/jobs/{records.job.id}")
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["result"]["face_count"], 4)

        artifact_detail = self.client.get(f"/api/v1/cad-artifacts/{records.artifact.id}")
        self.assertEqual(artifact_detail.status_code, 200)
        self.assertEqual(len(artifact_detail.json()["versions"]), 1)
        self.assertEqual(len(artifact_detail.json()["lineage"]), 1)
        self.assertEqual(artifact_detail.json()["lineage"][0]["relationship"], "derived_from")

        preview_url = status_response.json()["result"]["preview"]["download_url"]
        preview_response = self.client.get(preview_url)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_response["X-Content-Type-Options"], "nosniff")
        preview_response.close()

    def test_invalid_step_job_returns_typed_failure(self) -> None:
        invalid_step = b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;"
        upload = SimpleUploadedFile("invalid.step", invalid_step, content_type="model/step")
        records = create_upload_records(upload)

        task_result = process_cad_job.run(str(records.job.id))

        records.job.refresh_from_db()
        self.assertEqual(task_result["state"], "failed")
        self.assertEqual(records.job.state, Job.State.FAILED)
        self.assertEqual(records.job.error_code, "CAD_PARSE_INVALID_STEP")
        self.assertNotIn(str(Path(self.media_directory.name)), records.job.error_message)

        event_count = records.job.events.count()
        repeated_result = process_cad_job.run(str(records.job.id))
        self.assertEqual(repeated_result["state"], "failed")
        self.assertEqual(records.job.events.count(), event_count)


def test_step_parser_extracts_box_geometry(tmp_path: Path) -> None:
    source_path = tmp_path / "box.step"
    preview_path = tmp_path / "box.preview.stl"
    fixture_script = (
        "import cadquery as cq, os, sys; "
        "box=cq.Workplane('XY').box(10,20,30); "
        "cq.exporters.export(box, sys.argv[1], exportType='STEP'); "
        "sys.stdout.flush(); sys.stderr.flush(); os._exit(0)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", fixture_script, str(source_path)],
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0

    result = parse_cad_file(source_path, "step", preview_path)

    assert result.unit_system == "mm"
    assert result.volume == pytest.approx(6000)
    assert result.surface_area == pytest.approx(2200)
    assert result.face_count == 6
    assert result.edge_count == 12
    assert result.bounding_box["size"] == pytest.approx({"x": 10, "y": 20, "z": 30})
    assert result.surface_type_histogram == {"plane": 6}
    assert preview_path.exists()
