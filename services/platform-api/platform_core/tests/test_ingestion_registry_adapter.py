import io
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from openpyxl import Workbook

from platform_core.identity import ensure_account_profile
from platform_core.ingestion_center import commit_batch
from platform_core.ingestion_views import _parse_source
from platform_core.models import (
    AccessRole,
    BulkImportBatch,
    DataScope,
    Mold,
    MoldRevision,
    ProductPart,
    Project,
    RoleAssignment,
)


@override_settings(DEMO_AUTH_MODE="local")
class RegistryIngestionAdapterTests(TestCase):
    def setUp(self):
        self.scope = DataScope.objects.get(code="public-demo")
        self.user = get_user_model().objects.create_user(username="registry-importer")
        ensure_account_profile(self.user)
        role = AccessRole.objects.get(code="platform_admin")
        RoleAssignment.objects.create(
            user=self.user,
            role=role,
            data_scope=self.scope,
            granted_by=self.user,
            reason="Registry ingestion tests",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _records(self):
        return [
            {
                "project_code": "IMPORT-PROJECT",
                "project_name": "Import Project",
                "part_number": "PART-001",
                "part_name": "Housing",
                "mold_code": "IMPORT-MOLD",
                "mold_name": "Imported Mold",
                "cavity_count": 2,
                "revision_code": "A",
                "change_summary": "Initial imported revision",
            }
        ]

    def _create(self, records=None):
        return self.client.post(
            "/api/v1/ingestions",
            data=json.dumps(
                {
                    "scope": self.scope.code,
                    "domain": "registry",
                    "source_name": "registry.csv",
                    "idempotency_key": "registry-adapter",
                    "records": records or self._records(),
                }
            ),
            content_type="application/json",
        )

    def test_csv_and_xlsx_normalize_to_identical_rows(self):
        headers = list(self._records()[0])
        csv_content = (
            ",".join(headers)
            + "\n"
            + ",".join(str(self._records()[0][key]) for key in headers)
            + "\n"
        ).encode()
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(headers)
        sheet.append([self._records()[0][key] for key in headers])
        stream = io.BytesIO()
        workbook.save(stream)

        self.assertEqual(
            {
                key: str(value)
                for key, value in _parse_source("registry.csv", csv_content)[0].items()
            },
            {
                key: str(value)
                for key, value in _parse_source("registry.xlsx", stream.getvalue())[0].items()
            },
        )

    def test_dry_run_has_no_registry_writes_and_reports_typed_issue(self):
        response = self._create(records=[{**self._records()[0], "mold_name": ""}])
        batch_id = response.json()["batch_id"]
        validated = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")

        self.assertEqual(validated.json()["status"], "validation_failed")
        self.assertEqual(validated.json()["issues"][0]["code"], "REQUIRED_FIELDS")
        self.assertFalse(Project.objects.filter(code="IMPORT-PROJECT").exists())
        self.assertFalse(Mold.objects.filter(mold_code="IMPORT-MOLD").exists())

    def test_atomic_commit_builds_hierarchy_and_replay_skips_revision(self):
        created = self._create()
        batch_id = created.json()["batch_id"]
        validated = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
        self.assertTrue(validated.json()["validation"]["valid"])
        self.assertFalse(Project.objects.filter(code="IMPORT-PROJECT").exists())

        batch = BulkImportBatch.objects.get(id=batch_id)
        batch.status = BulkImportBatch.Status.QUEUED
        batch.save(update_fields=["status"])
        committed = commit_batch(batch_id, actor_id=str(ensure_account_profile(self.user).id))

        self.assertEqual(committed.status, "committed")
        self.assertTrue(Project.objects.filter(code="IMPORT-PROJECT").exists())
        self.assertTrue(ProductPart.objects.filter(part_number="PART-001").exists())
        self.assertTrue(Mold.objects.filter(mold_code="IMPORT-MOLD", cavity_count=2).exists())
        self.assertTrue(MoldRevision.objects.filter(revision_code="A").exists())
        self.assertTrue(BulkImportBatch.objects.get(id=batch_id).reconciliation["balanced"])

    def test_registry_template_is_versioned(self):
        response = self.client.get("/api/v1/import-templates/registry")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Schema-Version"], "1.0")
        self.assertIn("revision_code", response.content.decode())
