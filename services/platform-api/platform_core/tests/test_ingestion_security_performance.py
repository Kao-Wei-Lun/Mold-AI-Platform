import json
import time
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from openpyxl import Workbook

from platform_core.identity import ensure_account_profile
from platform_core.ingestion_center import commit_batch, persist_validation
from platform_core.models import (
    AccessRole,
    BulkImportBatch,
    DataScope,
    IngestionRecordResult,
    MasterDataItem,
    RoleAssignment,
)


@override_settings(DEMO_AUTH_MODE="local")
class IngestionSecurityTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name,
            MAX_INGESTION_UPLOAD_BYTES=25 * 1024 * 1024,
        )
        self.settings_override.enable()
        self.scope = DataScope.objects.get(code="public-demo")
        self.user = get_user_model().objects.create_user(
            username="ingestion-security", password="Ingestion-Security-2026!"
        )
        ensure_account_profile(self.user)
        role = AccessRole.objects.get(code="platform_admin")
        RoleAssignment.objects.create(
            user=self.user,
            role=role,
            data_scope=self.scope,
            granted_by=self.user,
            reason="Ingestion security test",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def create_batch(self, key: str) -> str:
        response = self.client.post(
            "/api/v1/ingestions",
            data=json.dumps(
                {
                    "scope": "public-demo",
                    "domain": "master_data",
                    "source_name": "security.csv",
                    "idempotency_key": key,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["batch_id"]

    def upload(self, batch_id: str, name: str, content: bytes, mime: str):
        return self.client.post(
            f"/api/v1/ingestions/{batch_id}/files",
            {"file": SimpleUploadedFile(name, content, content_type=mime)},
        )

    def workbook_bytes(self, *, formula: bool = False, hidden: bool = False) -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["kind", "code", "name_en"])
        sheet.append(
            [
                "material",
                "XLSX-ABS",
                '=HYPERLINK("https://example.test","x")' if formula else "XLSX ABS",
            ]
        )
        if hidden:
            hidden_sheet = workbook.create_sheet("hidden")
            hidden_sheet.sheet_state = "hidden"
        stream = BytesIO()
        workbook.save(stream)
        workbook.close()
        return stream.getvalue()

    def test_rejects_csv_and_xlsx_formula_injection(self):
        csv_batch = self.create_batch("formula-csv")
        csv_response = self.upload(
            csv_batch,
            "formula.csv",
            b'kind,code,name_en\nmaterial,CSV-FORMULA,=WEBSERVICE("https://example.test")\n',
            "text/csv",
        )
        self.assertEqual(csv_response.status_code, 400)
        self.assertEqual(csv_response.json()["error"]["code"], "IMPORT_FORMULA_INJECTION")

        xlsx_batch = self.create_batch("formula-xlsx")
        xlsx_response = self.upload(
            xlsx_batch,
            "formula.xlsx",
            self.workbook_bytes(formula=True),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertEqual(xlsx_response.status_code, 400)
        self.assertEqual(xlsx_response.json()["error"]["code"], "IMPORT_FORMULA_INJECTION")

    def test_rejects_hidden_xlsx_content_mime_spoof_and_oversized_source(self):
        hidden_batch = self.create_batch("hidden-xlsx")
        hidden_response = self.upload(
            hidden_batch,
            "hidden.xlsx",
            self.workbook_bytes(hidden=True),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertEqual(hidden_response.status_code, 400)
        self.assertEqual(hidden_response.json()["error"]["code"], "IMPORT_XLSX_HIDDEN_CONTENT")

        mime_batch = self.create_batch("mime-spoof")
        mime_response = self.upload(
            mime_batch,
            "spoof.csv",
            b"kind,code,name_en\nmaterial,MIME,MIME\n",
            "image/png",
        )
        self.assertEqual(mime_response.status_code, 400)
        self.assertEqual(mime_response.json()["error"]["code"], "IMPORT_MIME_MISMATCH")

        with override_settings(MAX_INGESTION_UPLOAD_BYTES=8):
            size_batch = self.create_batch("oversized")
            size_response = self.upload(
                size_batch,
                "large.csv",
                b"kind,code,name_en\nmaterial,LARGE,LARGE\n",
                "text/csv",
            )
        self.assertEqual(size_response.status_code, 400)
        self.assertEqual(size_response.json()["error"]["code"], "IMPORT_FILE_TOO_LARGE")

    def test_sanitizes_path_names_and_enforces_csrf_on_mutation(self):
        batch_id = self.create_batch("path-name")
        response = self.upload(
            batch_id,
            "../materials.csv",
            b"kind,code,name_en\nmaterial,SAFE,Safe\n",
            "text/csv",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["source_files"][0]["file_name"], "materials.csv")

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        denied = csrf_client.post(
            "/api/v1/ingestions",
            data=json.dumps(
                {
                    "scope": "public-demo",
                    "domain": "master_data",
                    "source_name": "csrf",
                    "idempotency_key": "csrf-denied",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)


class IngestionPerformanceTests(TestCase):
    def test_master_data_10k_dry_run_and_commit_each_complete_within_60_seconds(self):
        scope = DataScope.objects.get(code="public-demo")
        records = [
            {"kind": "material", "code": f"PERF-{index:05d}", "name_en": f"Material {index}"}
            for index in range(10_000)
        ]
        batch = BulkImportBatch.objects.create(
            scope=scope,
            domain="master_data",
            source_name="performance-10k",
            idempotency_key="performance-10k",
            records=records,
            classification=scope.classification,
            created_by="performance-test",
        )

        validation_started = time.monotonic()
        validation = persist_validation(batch)
        validation_seconds = time.monotonic() - validation_started
        self.assertTrue(validation["valid"])
        self.assertLessEqual(validation_seconds, 60)

        batch.refresh_from_db()
        batch.status = BulkImportBatch.Status.QUEUED
        batch.save(update_fields=["status", "updated_at"])
        commit_started = time.monotonic()
        committed = commit_batch(str(batch.id), actor_id="performance-test")
        commit_seconds = time.monotonic() - commit_started

        self.assertLessEqual(commit_seconds, 60)
        self.assertEqual(committed.status, BulkImportBatch.Status.COMMITTED)
        self.assertTrue(committed.reconciliation["balanced"])
        self.assertEqual(committed.reconciliation["created_count"], 10_000)
        self.assertEqual(MasterDataItem.objects.filter(code__startswith="PERF-").count(), 10_000)
        self.assertEqual(IngestionRecordResult.objects.filter(batch=batch).count(), 10_000)
