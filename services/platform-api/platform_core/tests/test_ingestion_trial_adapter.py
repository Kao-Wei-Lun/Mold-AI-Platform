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
    MasterDataItem,
    ProcessParameter,
    ProcessRun,
    RoleAssignment,
    TrialCase,
)


@override_settings(DEMO_AUTH_MODE="local")
class TrialIngestionAdapterTests(TestCase):
    def setUp(self):
        self.scope = DataScope.objects.get(code="public-demo")
        self.user = get_user_model().objects.create_user(username="trial-importer")
        ensure_account_profile(self.user)
        RoleAssignment.objects.create(
            user=self.user,
            role=AccessRole.objects.get(code="platform_admin"),
            data_scope=self.scope,
            granted_by=self.user,
            reason="Trial ingestion tests",
        )
        self.client = Client()
        self.client.force_login(self.user)
        for kind, code in (
            (MasterDataItem.Kind.MACHINE, "IMPORT-MACHINE"),
            (MasterDataItem.Kind.MATERIAL, "IMPORT-ABS"),
            (MasterDataItem.Kind.PRODUCT_TYPE, "IMPORT-HOUSING"),
            (MasterDataItem.Kind.UNIT, "IMPORT-MPA"),
        ):
            MasterDataItem.objects.create(
                scope=self.scope,
                kind=kind,
                code=code,
                name_en=code,
                name_zh_tw=code,
                created_by="test",
                updated_by="test",
            )

    def _record(self):
        return {
            "case_code": "IMPORT-TRIAL-001",
            "mold_revision_ref": "IMPORT-MOLD@A",
            "part_revision_ref": "PART-001@A",
            "machine_code": "IMPORT-MACHINE",
            "material_code": "IMPORT-ABS",
            "product_type": "IMPORT-HOUSING",
            "purpose": "Initial parameter validation",
            "outcome": "pending",
            "started_at": "2026-08-30T09:00:00+08:00",
            "run_number": 1,
            "result": "pending",
            "parameter_code": "injection_pressure",
            "parameter_value": 88.5,
            "parameter_unit": "IMPORT-MPA",
            "value_kind": "setpoint",
        }

    def _create(self, records=None):
        return self.client.post(
            "/api/v1/ingestions",
            data=json.dumps(
                {
                    "scope": self.scope.code,
                    "domain": "trials",
                    "source_name": "trials.xlsx",
                    "idempotency_key": "trial-import",
                    "records": records or [self._record()],
                }
            ),
            content_type="application/json",
        )

    def test_csv_xlsx_and_json_formats_are_accepted(self):
        record = self._record()
        headers = list(record)
        csv_bytes = (
            ",".join(headers) + "\n" + ",".join(str(record[key]) for key in headers) + "\n"
        ).encode()
        workbook = Workbook()
        workbook.active.append(headers)
        workbook.active.append([record[key] for key in headers])
        stream = io.BytesIO()
        workbook.save(stream)
        self.assertEqual(len(_parse_source("trials.csv", csv_bytes)), 1)
        self.assertEqual(len(_parse_source("trials.xlsx", stream.getvalue())), 1)
        self.assertEqual(len(_parse_source("trials.json", json.dumps([record]).encode())), 1)

    def test_dry_run_reports_row_and_writes_no_trial(self):
        record = {**self._record(), "started_at": "not-a-date"}
        batch_id = self._create([record]).json()["batch_id"]
        validated = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
        self.assertEqual(validated.json()["issues"][0]["code"], "INVALID_DATETIME")
        self.assertFalse(TrialCase.objects.filter(case_code="IMPORT-TRIAL-001").exists())

    def test_commit_creates_draft_trial_run_and_parameter(self):
        batch_id = self._create().json()["batch_id"]
        validated = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
        self.assertTrue(validated.json()["validation"]["valid"])
        batch = BulkImportBatch.objects.get(id=batch_id)
        batch.status = BulkImportBatch.Status.QUEUED
        batch.save(update_fields=["status"])
        commit_batch(batch_id, actor_id=str(ensure_account_profile(self.user).id))

        trial = TrialCase.objects.get(case_code="IMPORT-TRIAL-001")
        self.assertEqual(trial.lifecycle_status, TrialCase.LifecycleStatus.DRAFT)
        run = ProcessRun.objects.get(trial=trial, run_number=1)
        self.assertTrue(
            ProcessParameter.objects.filter(
                process_run=run, canonical_code="injection_pressure", value_kind="setpoint"
            ).exists()
        )
        self.assertTrue(BulkImportBatch.objects.get(id=batch_id).reconciliation["balanced"])

    def test_trial_template_is_versioned(self):
        response = self.client.get("/api/v1/import-templates/trials")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Schema-Version"], "1.0")
        self.assertIn("parameter_code", response.content.decode())
