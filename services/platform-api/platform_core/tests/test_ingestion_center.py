import json
from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from platform_core.identity import ensure_account_profile
from platform_core.job_recovery import recover_stale_jobs
from platform_core.models import (
    AccessRole,
    BulkImportBatch,
    DataScope,
    IngestionRecordResult,
    MasterDataItem,
    RoleAssignment,
)
from platform_core.tasks import commit_ingestion_job


@override_settings(DEMO_AUTH_MODE="local")
class IngestionCenterTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        self.scope = DataScope.objects.get(code="public-demo")
        self.other_scope = DataScope.objects.create(
            code="company-ingestion",
            name="Company ingestion",
            classification="company_confidential",
        )
        self.user = get_user_model().objects.create_user(
            username="ingestion-admin", password="Ingestion-Test-2026!"
        )
        ensure_account_profile(self.user)
        role = AccessRole.objects.get(code="platform_admin")
        role.permissions = sorted(
            set(role.permissions)
            | {
                "ingestion:read",
                "ingestion:create",
                "ingestion:validate",
                "ingestion:commit",
                "ingestion:cancel",
            }
        )
        role.save(update_fields=["permissions"])
        RoleAssignment.objects.create(
            user=self.user,
            role=role,
            data_scope=self.scope,
            granted_by=self.user,
            reason="Ingestion test",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def create_batch(self, *, key="ingestion-1", records=None):
        return self.client.post(
            "/api/v1/ingestions",
            data=json.dumps(
                {
                    "scope": "public-demo",
                    "domain": "master_data",
                    "source_name": "materials",
                    "idempotency_key": key,
                    "records": records
                    or [{"kind": "material", "code": "ING-ABS", "name_en": "Ingestion ABS"}],
                }
            ),
            content_type="application/json",
        )

    def test_dry_run_creates_no_domain_entities_and_persists_typed_issues(self):
        created = self.create_batch(
            records=[{"kind": "material", "code": "MISSING-NAME", "name_en": ""}]
        )
        self.assertEqual(created.status_code, 201)
        batch_id = created.json()["batch_id"]
        self.assertFalse(MasterDataItem.objects.filter(code="MISSING-NAME").exists())

        validated = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
        self.assertEqual(validated.status_code, 200)
        self.assertEqual(validated.json()["status"], "validation_failed")
        self.assertEqual(validated.json()["issues"][0]["code"], "REQUIRED_FIELDS")
        self.assertFalse(MasterDataItem.objects.filter(code="MISSING-NAME").exists())

    def test_csv_upload_mapping_validate_and_background_commit(self):
        created = self.client.post(
            "/api/v1/ingestions",
            data=json.dumps(
                {
                    "scope": "public-demo",
                    "domain": "master_data",
                    "source_name": "materials.csv",
                    "idempotency_key": "csv-ingestion",
                }
            ),
            content_type="application/json",
        ).json()
        batch_id = created["batch_id"]
        uploaded = self.client.post(
            f"/api/v1/ingestions/{batch_id}/files",
            {
                "file": SimpleUploadedFile(
                    "materials.csv",
                    b"type,identifier,label\nmaterial,CSV-ABS,CSV ABS\n",
                    content_type="text/csv",
                )
            },
        )
        self.assertEqual(uploaded.status_code, 201)
        self.assertEqual(uploaded.json()["status"], "mapping_required")
        self.assertEqual(len(uploaded.json()["source_files"]), 1)

        mapped = self.client.put(
            f"/api/v1/ingestions/{batch_id}/mapping",
            data=json.dumps(
                {"field_mapping": {"kind": "type", "code": "identifier", "name_en": "label"}}
            ),
            content_type="application/json",
        )
        self.assertEqual(mapped.status_code, 200)
        validated = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
        self.assertTrue(validated.json()["validation"]["valid"])
        self.assertFalse(MasterDataItem.objects.filter(code="CSV-ABS").exists())

        with patch("platform_core.ingestion_views.commit_ingestion_job.apply_async") as queued:
            with self.captureOnCommitCallbacks(execute=True):
                accepted = self.client.post(
                    f"/api/v1/ingestions/{batch_id}/commit",
                    data=json.dumps({"reason": "Validated by ingestion operator"}),
                    content_type="application/json",
                )
        self.assertEqual(accepted.status_code, 202)
        queued.assert_called_once()
        result = commit_ingestion_job.run(
            accepted.json()["job_id"], batch_id, str(ensure_account_profile(self.user).id)
        )
        self.assertEqual(result["status"], "committed")
        batch = BulkImportBatch.objects.get(id=batch_id)
        self.assertEqual(batch.status, BulkImportBatch.Status.COMMITTED)
        self.assertTrue(batch.reconciliation["balanced"])
        self.assertTrue(MasterDataItem.objects.filter(code="CSV-ABS").exists())
        self.assertEqual(IngestionRecordResult.objects.filter(batch=batch).count(), 1)

    def test_idempotency_replay_and_scope_isolation(self):
        first = self.create_batch(key="stable-key")
        replay = self.create_batch(key="stable-key")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.json()["batch_id"], replay.json()["batch_id"])

        hidden = BulkImportBatch.objects.create(
            scope=self.other_scope,
            domain="master_data",
            source_name="secret",
            idempotency_key="other-scope-key",
            created_by="other",
        )
        detail = self.client.get(f"/api/v1/ingestions/{hidden.id}")
        self.assertEqual(detail.status_code, 404)

    def test_atomic_commit_rolls_back_every_domain_write_on_failure(self):
        batch_id = self.create_batch(
            key="rollback-ingestion",
            records=[
                {"kind": "material", "code": "ROLLBACK-A", "name_en": "Rollback A"},
                {"kind": "material", "code": "ROLLBACK-B", "name_en": "Rollback B"},
            ],
        ).json()["batch_id"]
        self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
        with patch("platform_core.ingestion_views.commit_ingestion_job.apply_async"):
            with self.captureOnCommitCallbacks(execute=True):
                accepted = self.client.post(
                    f"/api/v1/ingestions/{batch_id}/commit",
                    data=json.dumps({"reason": "Atomic rollback test"}),
                    content_type="application/json",
                ).json()
        actual_create = MasterDataItem.objects.create
        calls = 0

        def fail_second_create(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated second-row failure")
            return actual_create(**kwargs)

        with patch(
            "platform_core.ingestion_adapters.MasterDataItem.objects.create",
            side_effect=fail_second_create,
        ):
            result = commit_ingestion_job.run(
                accepted["job_id"], batch_id, str(ensure_account_profile(self.user).id)
            )

        self.assertEqual(result["status"], "failed")
        self.assertFalse(
            MasterDataItem.objects.filter(code__in=["ROLLBACK-A", "ROLLBACK-B"]).exists()
        )
        self.assertEqual(
            BulkImportBatch.objects.get(id=batch_id).status, BulkImportBatch.Status.FAILED
        )

    @patch("platform_core.job_recovery.current_app.send_task")
    def test_stale_ingestion_job_requeues_with_complete_task_arguments(self, send_task):
        batch_id = self.create_batch(key="stale-ingestion").json()["batch_id"]
        self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
        with patch("platform_core.ingestion_views.commit_ingestion_job.apply_async"):
            with self.captureOnCommitCallbacks(execute=True):
                accepted = self.client.post(
                    f"/api/v1/ingestions/{batch_id}/commit",
                    data=json.dumps({"reason": "Queue for recovery"}),
                    content_type="application/json",
                ).json()
        batch = BulkImportBatch.objects.get(id=batch_id)
        batch.job.created_at = timezone.now() - timedelta(minutes=30)
        batch.job.save(update_fields=["created_at"])

        result = recover_stale_jobs(stale_minutes=15, apply=True)

        self.assertEqual(result["actions"]["requeued"], 1)
        send_task.assert_called_once_with(
            "platform_core.commit_ingestion_job",
            args=[accepted["job_id"], batch_id, batch.created_by],
            queue="general",
        )
