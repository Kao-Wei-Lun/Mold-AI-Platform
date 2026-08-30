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
    RoleAssignment,
    RuleProfile,
    RuleVersion,
)


@override_settings(DEMO_AUTH_MODE="local")
class RuleProfileIngestionAdapterTests(TestCase):
    def setUp(self):
        self.scope = DataScope.objects.get(code="public-demo")
        self.user = get_user_model().objects.create_user(username="rule-importer")
        ensure_account_profile(self.user)
        RoleAssignment.objects.create(
            user=self.user,
            role=AccessRole.objects.get(code="platform_admin"),
            data_scope=self.scope,
            granted_by=self.user,
            reason="Rule ingestion tests",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _record(self):
        return {
            "profile_key": "imported-three-plate",
            "version": "1.0",
            "rule_id": "IMPORT-DRAFT-001",
            "title": "Imported draft angle",
            "description": "Draft angle must meet the configured limit.",
            "evaluator": "context_value",
            "operator": "gte",
            "limit_value": 1.0,
            "unit": "deg",
            "tolerance": 0,
            "severity": "high",
            "risk_type": "release",
            "recommendation": "Increase draft angle.",
        }

    def _create(self, records=None, key="rule-import"):
        return self.client.post(
            "/api/v1/ingestions",
            data=json.dumps(
                {
                    "scope": self.scope.code,
                    "domain": "rule_profiles",
                    "source_name": "rules.xlsx",
                    "idempotency_key": key,
                    "records": records or [self._record()],
                }
            ),
            content_type="application/json",
        )

    def test_json_csv_and_xlsx_share_canonical_shape(self):
        record = self._record()
        headers = list(record)
        csv_bytes = (
            ",".join(headers) + "\n" + ",".join(str(record[key]) for key in headers) + "\n"
        ).encode()
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(headers)
        sheet.append([record[key] for key in headers])
        stream = io.BytesIO()
        workbook.save(stream)
        json_row = _parse_source("rules.json", json.dumps([record]).encode())[0]
        csv_row = _parse_source("rules.csv", csv_bytes)[0]
        xlsx_row = _parse_source("rules.xlsx", stream.getvalue())[0]
        self.assertEqual(set(json_row), set(csv_row))
        self.assertEqual(set(json_row), set(xlsx_row))

    def test_dry_run_rejects_unknown_evaluator_without_writes(self):
        batch_id = self._create(records=[{**self._record(), "evaluator": "run_python"}]).json()[
            "batch_id"
        ]
        validated = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
        self.assertEqual(validated.json()["issues"][0]["code"], "INVALID_RULE")
        self.assertFalse(RuleProfile.objects.filter(profile_key="imported-three-plate").exists())

    def test_commit_creates_draft_and_cannot_publish_by_import(self):
        batch_id = self._create().json()["batch_id"]
        validated = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
        self.assertTrue(validated.json()["validation"]["valid"])
        batch = BulkImportBatch.objects.get(id=batch_id)
        batch.status = BulkImportBatch.Status.QUEUED
        batch.save(update_fields=["status"])
        commit_batch(batch_id, actor_id=str(ensure_account_profile(self.user).id))

        profile = RuleProfile.objects.get(profile_key="imported-three-plate")
        self.assertEqual(profile.workflow_status, RuleProfile.WorkflowStatus.DRAFT)
        self.assertFalse(profile.published_at)
        self.assertTrue(
            RuleVersion.objects.filter(profile=profile, rule_id="IMPORT-DRAFT-001").exists()
        )
        self.assertTrue(BulkImportBatch.objects.get(id=batch_id).reconciliation["balanced"])

    def test_rule_template_is_versioned(self):
        response = self.client.get("/api/v1/import-templates/rule_profiles")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Schema-Version"], "1.0")
        self.assertIn("profile_key", response.content.decode())
