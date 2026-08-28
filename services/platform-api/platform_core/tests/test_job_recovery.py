from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from platform_core.ingestion import create_upload_records
from platform_core.job_recovery import recover_stale_jobs
from platform_core.models import AuditEvent, Job, JobEvent

from .fixtures import ASCII_TETRAHEDRON_STL


class StaleJobRecoveryTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    def create_job(self) -> Job:
        records = create_upload_records(
            SimpleUploadedFile("part.stl", ASCII_TETRAHEDRON_STL, content_type="model/stl")
        )
        Job.objects.filter(pk=records.job.id).update(
            created_at=timezone.now() - timedelta(minutes=30)
        )
        return Job.objects.get(pk=records.job.id)

    @patch("platform_core.job_recovery.current_app.send_task")
    def test_dry_run_is_read_only(self, send_task) -> None:
        job = self.create_job()

        result = recover_stale_jobs(stale_minutes=15)

        job.refresh_from_db()
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["counts"]["queued"], 1)
        self.assertEqual(job.stage, "queued")
        send_task.assert_not_called()
        self.assertEqual(AuditEvent.objects.count(), 0)

    @patch("platform_core.job_recovery.current_app.send_task")
    def test_stale_queued_job_is_requeued_and_audited(self, send_task) -> None:
        job = self.create_job()

        result = recover_stale_jobs(stale_minutes=15, apply=True)

        job.refresh_from_db()
        self.assertEqual(result["actions"]["requeued"], 1)
        self.assertEqual(job.state, Job.State.QUEUED)
        self.assertEqual(job.stage, "recovery_requeued")
        send_task.assert_called_once_with(
            "platform_core.process_cad_job", args=[str(job.id)], queue="cad"
        )
        self.assertTrue(JobEvent.objects.filter(job=job, stage="recovery_requeued").exists())
        self.assertTrue(AuditEvent.objects.filter(event_type="demo.stale_job_recovery.v1").exists())

    @patch("platform_core.job_recovery.current_app.send_task")
    def test_exhausted_running_job_fails_without_requeue(self, send_task) -> None:
        job = self.create_job()
        Job.objects.filter(pk=job.id).update(
            state=Job.State.RUNNING,
            stage="parsing_geometry",
            attempt=1,
            max_attempts=1,
            started_at=timezone.now() - timedelta(minutes=30),
            heartbeat_at=timezone.now() - timedelta(minutes=30),
        )

        result = recover_stale_jobs(stale_minutes=15, apply=True)

        job.refresh_from_db()
        self.assertEqual(result["actions"]["failed"], 1)
        self.assertEqual(job.state, Job.State.FAILED)
        self.assertEqual(job.error_code, "JOB_HEARTBEAT_EXPIRED")
        self.assertEqual(job.input_artifact_version.cad_model.geometry_status, "failed")
        send_task.assert_not_called()

    @patch("platform_core.job_recovery.current_app.send_task")
    def test_running_job_below_attempt_limit_is_requeued(self, send_task) -> None:
        job = self.create_job()
        Job.objects.filter(pk=job.id).update(
            state=Job.State.RUNNING,
            attempt=1,
            max_attempts=2,
            started_at=timezone.now() - timedelta(minutes=30),
            heartbeat_at=timezone.now() - timedelta(minutes=30),
        )

        result = recover_stale_jobs(stale_minutes=15, apply=True)

        job.refresh_from_db()
        self.assertEqual(result["actions"]["requeued"], 1)
        self.assertEqual(job.state, Job.State.QUEUED)
        self.assertIsNone(job.started_at)
        self.assertIsNone(job.heartbeat_at)
        send_task.assert_called_once()

    @patch("platform_core.job_recovery.current_app.send_task", side_effect=ConnectionError)
    def test_queue_failure_is_typed(self, send_task) -> None:
        job = self.create_job()

        result = recover_stale_jobs(stale_minutes=15, apply=True)

        job.refresh_from_db()
        self.assertEqual(result["actions"]["queue_failures"], 1)
        self.assertEqual(job.state, Job.State.FAILED)
        self.assertEqual(job.error_code, "JOB_RECOVERY_QUEUE_UNAVAILABLE")

    def test_management_command_requires_exact_confirmation(self) -> None:
        with self.assertRaises(CommandError):
            call_command("recover_stale_jobs", "--apply", confirmation="wrong")
