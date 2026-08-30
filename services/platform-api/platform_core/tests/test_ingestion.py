import hashlib
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from platform_core.models import (
    Artifact,
    ArtifactVersion,
    CADModel,
    DataScope,
    Job,
    Mold,
    MoldRevision,
    Project,
)

from .fixtures import ASCII_TETRAHEDRON_STL


class CADUploadEndpointTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    @staticmethod
    def upload_file(content: bytes = ASCII_TETRAHEDRON_STL, name: str = "part.stl"):
        return SimpleUploadedFile(name, content, content_type="model/stl")

    @patch("platform_core.views.process_cad_job.apply_async")
    def test_upload_creates_version_model_and_queued_job(self, apply_async) -> None:
        response = self.client.post(
            "/api/v1/cad-artifacts",
            {
                "file": self.upload_file(),
                "artifact_name": "Demo tetrahedron",
                "idempotency_key": "upload-tetra-v1",
            },
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["ingestion_mode"], "quick_analysis")
        self.assertEqual(payload["governance_status"], "unassigned")
        self.assertIsNone(payload["mold_revision_id"])
        self.assertFalse(payload["idempotent_replay"])
        self.assertEqual(Artifact.objects.count(), 1)
        self.assertEqual(ArtifactVersion.objects.count(), 1)
        self.assertEqual(CADModel.objects.count(), 1)
        self.assertEqual(Job.objects.count(), 1)

        version = ArtifactVersion.objects.get()
        self.assertEqual(version.sha256, hashlib.sha256(ASCII_TETRAHEDRON_STL).hexdigest())
        self.assertEqual(version.malware_status, ArtifactVersion.MalwareStatus.BASIC_SCREENED)
        self.assertNotIn(version.original_filename, version.storage_key)
        apply_async.assert_called_once_with(args=[payload["job_id"]], queue="cad")

        artifact = Artifact.objects.get()
        self.assertIsNone(artifact.mold_revision_id)
        self.assertEqual(
            Job.objects.get().input_snapshot["source"],
            {
                "type": "manual_upload",
                "version_action": "new_artifact",
                "ingestion_mode": "quick_analysis",
                "governance_status": "unassigned",
            },
        )
        job_response = self.client.get(payload["links"]["status"])
        self.assertEqual(job_response.status_code, 200)
        self.assertEqual(job_response.json()["state"], "queued")

    @patch("platform_core.views.process_cad_job.apply_async")
    def test_new_version_preserves_prior_artifact_version_and_results(self, apply_async) -> None:
        first = self.client.post(
            "/api/v1/cad-artifacts",
            {
                "file": self.upload_file(),
                "artifact_name": "Versioned mold CAD",
                "idempotency_key": "cad-version-1",
            },
        )
        artifact_id = first.json()["artifact_id"]
        first_version_id = first.json()["artifact_version_id"]
        second = self.client.post(
            "/api/v1/cad-artifacts",
            {
                "file": self.upload_file(name="part-v2.stl"),
                "artifact_id": artifact_id,
                "ingestion_mode": "quick_analysis",
                "idempotency_key": "cad-version-2",
            },
        )

        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.json()["version_action"], "new_version")
        self.assertEqual(second.json()["version_number"], 2)
        self.assertEqual(Artifact.objects.count(), 1)
        self.assertEqual(ArtifactVersion.objects.count(), 2)
        latest = ArtifactVersion.objects.get(id=second.json()["artifact_version_id"])
        self.assertEqual(str(latest.supersedes_id), first_version_id)
        self.assertTrue(ArtifactVersion.objects.filter(id=first_version_id).exists())
        self.assertEqual(CADModel.objects.count(), 2)
        self.assertEqual(apply_async.call_count, 2)

    @patch("platform_core.views.process_cad_job.apply_async")
    def test_new_version_rejects_governance_mode_change(self, apply_async) -> None:
        first = self.client.post(
            "/api/v1/cad-artifacts",
            {"file": self.upload_file(), "idempotency_key": "cad-mode-v1"},
        )
        response = self.client.post(
            "/api/v1/cad-artifacts",
            {
                "file": self.upload_file(name="part-v2.stl"),
                "artifact_id": first.json()["artifact_id"],
                "ingestion_mode": "governed_archive",
                "idempotency_key": "cad-mode-v2",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_INGESTION_MODE")
        self.assertEqual(ArtifactVersion.objects.count(), 1)

    @patch("platform_core.views.process_cad_job.apply_async")
    def test_governed_archive_requires_mold_revision(self, apply_async) -> None:
        response = self.client.post(
            "/api/v1/cad-artifacts",
            {
                "file": self.upload_file(),
                "ingestion_mode": "governed_archive",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_MOLD_REVISION_REQUIRED")
        self.assertEqual(Artifact.objects.count(), 0)
        apply_async.assert_not_called()

    @patch("platform_core.views.process_cad_job.apply_async")
    def test_governed_archive_links_artifact_to_revision(self, apply_async) -> None:
        scope, _ = DataScope.objects.get_or_create(
            code="cad-upload-test",
            defaults={"name": "CAD upload test", "classification": "public_demo"},
        )
        project = Project.objects.create(scope=scope, code="CAD-UPLOAD", name="CAD upload")
        mold = Mold.objects.create(project=project, mold_code="MOLD-UPLOAD", name="Upload mold")
        revision = MoldRevision.objects.create(
            mold=mold,
            revision_code="A",
            status=MoldRevision.Status.RELEASED,
        )

        response = self.client.post(
            "/api/v1/cad-artifacts",
            {
                "file": self.upload_file(),
                "ingestion_mode": "governed_archive",
                "mold_revision_id": str(revision.id),
            },
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["ingestion_mode"], "governed_archive")
        self.assertEqual(payload["governance_status"], "governed")
        self.assertEqual(payload["mold_revision_id"], str(revision.id))
        self.assertEqual(Artifact.objects.get().mold_revision_id, revision.id)
        self.assertEqual(
            Job.objects.get().input_snapshot["source"]["governance_status"], "governed"
        )
        apply_async.assert_called_once()

    @patch("platform_core.views.process_cad_job.apply_async")
    def test_rejects_unknown_ingestion_mode(self, apply_async) -> None:
        response = self.client.post(
            "/api/v1/cad-artifacts",
            {
                "file": self.upload_file(),
                "ingestion_mode": "temporary",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_INGESTION_MODE")
        apply_async.assert_not_called()

    @patch("platform_core.views.process_cad_job.apply_async")
    def test_idempotency_key_returns_original_job_without_requeue(self, apply_async) -> None:
        request_data = {"file": self.upload_file(), "idempotency_key": "stable-key"}
        first = self.client.post("/api/v1/cad-artifacts", request_data)
        second = self.client.post(
            "/api/v1/cad-artifacts",
            {"file": self.upload_file(), "idempotency_key": "stable-key"},
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.json()["job_id"], second.json()["job_id"])
        self.assertTrue(second.json()["idempotent_replay"])
        apply_async.assert_called_once()

    @patch("platform_core.views.process_cad_job.apply_async")
    def test_rejects_extension_content_mismatch(self, apply_async) -> None:
        response = self.client.post(
            "/api/v1/cad-artifacts",
            {"file": self.upload_file(b"not a mesh", "fake.step")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_FILE_SIGNATURE")
        self.assertEqual(Artifact.objects.count(), 0)
        apply_async.assert_not_called()

    @patch("platform_core.views.process_cad_job.apply_async")
    def test_rejects_eicar_test_marker(self, apply_async) -> None:
        malicious = ASCII_TETRAHEDRON_STL + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
        response = self.client.post(
            "/api/v1/cad-artifacts",
            {"file": self.upload_file(malicious)},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_MALWARE_TEST_SIGNATURE")
        apply_async.assert_not_called()

    @patch("platform_core.views.process_cad_job.apply_async")
    def test_artifact_version_content_fields_are_immutable(self, apply_async) -> None:
        response = self.client.post(
            "/api/v1/cad-artifacts",
            {"file": self.upload_file()},
        )
        self.assertEqual(response.status_code, 202)

        version = ArtifactVersion.objects.get()
        version.sha256 = "0" * 64
        with self.assertRaises(ValidationError):
            version.save()

    @patch("platform_core.views.process_cad_job.apply_async", side_effect=ConnectionError)
    def test_queue_failure_returns_503_and_marks_job_failed(self, apply_async) -> None:
        response = self.client.post(
            "/api/v1/cad-artifacts",
            {"file": self.upload_file()},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "JOB_QUEUE_UNAVAILABLE")
        job = Job.objects.get()
        self.assertEqual(job.state, Job.State.FAILED)
        self.assertEqual(job.error_code, "JOB_QUEUE_UNAVAILABLE")
        self.assertEqual(job.input_artifact_version.cad_model.geometry_status, "failed")
        apply_async.assert_called_once()
