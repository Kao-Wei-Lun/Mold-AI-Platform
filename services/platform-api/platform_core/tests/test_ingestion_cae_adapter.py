import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from platform_core.identity import ensure_account_profile
from platform_core.ingestion_center import commit_batch
from platform_core.models import (
    AccessRole,
    BulkImportBatch,
    CAEResult,
    CAERun,
    CAEStudy,
    DataScope,
    MasterDataItem,
    RoleAssignment,
)


@override_settings(DEMO_AUTH_MODE="local")
class CAEIngestionAdapterTests(TestCase):
    def setUp(self):
        self.scope = DataScope.objects.get(code="public-demo")
        self.user = get_user_model().objects.create_user(username="cae-importer")
        ensure_account_profile(self.user)
        RoleAssignment.objects.create(
            user=self.user,
            role=AccessRole.objects.get(code="platform_admin"),
            data_scope=self.scope,
            granted_by=self.user,
            reason="CAE ingestion tests",
        )
        self.client = Client()
        self.client.force_login(self.user)
        MasterDataItem.objects.get_or_create(
            scope=self.scope,
            kind=MasterDataItem.Kind.UNIT,
            code="IMPORT-SECOND",
            defaults={
                "name_en": "Second",
                "name_zh_tw": "秒",
                "created_by": "test",
                "updated_by": "test",
            },
        )

    def _record(self):
        return {
            "study_code": "IMPORT-CAE-001",
            "solver_name": "Moldflow",
            "product_ref": "PART-001@A",
            "mold_revision_ref": "MOLD-001@A",
            "material_model_code": "ABS-DEMO",
            "mesh_family": "3D",
            "objective": "Validate fill time",
            "run_code": "RUN-001",
            "solver_version": "2026",
            "mesh_artifact_ref": "mesh:001",
            "mesh_checksum": "a" * 64,
            "boundary_settings": {"mold_temperature": 60},
            "process_settings": {"melt_temperature": 240},
            "unit_system": "SI",
            "status": "succeeded",
            "metric_code": "fill_time",
            "result_type": "scalar",
            "value": 1.42,
            "unit": "IMPORT-SECOND",
            "location": {},
            "field_summary": {"p95": 1.4},
        }

    def _create(self, records=None):
        return self.client.post(
            "/api/v1/ingestions",
            data=json.dumps(
                {
                    "scope": self.scope.code,
                    "domain": "cae_results",
                    "source_name": "cae-summary.json",
                    "idempotency_key": "cae-import",
                    "records": records or [self._record()],
                }
            ),
            content_type="application/json",
        )

    def test_dry_run_rejects_invalid_settings_without_domain_writes(self):
        batch_id = self._create([{**self._record(), "boundary_settings": "not-json"}]).json()[
            "batch_id"
        ]
        response = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
        self.assertEqual(response.json()["issues"][0]["code"], "INVALID_CAE_RESULT")
        self.assertFalse(CAEStudy.objects.filter(study_code="IMPORT-CAE-001").exists())

    def test_commit_creates_append_only_study_run_result(self):
        batch_id = self._create().json()["batch_id"]
        validated = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
        self.assertTrue(validated.json()["validation"]["valid"])
        batch = BulkImportBatch.objects.get(id=batch_id)
        batch.status = BulkImportBatch.Status.QUEUED
        batch.save(update_fields=["status"])
        commit_batch(batch_id, actor_id=str(ensure_account_profile(self.user).id))

        study = CAEStudy.objects.get(study_code="IMPORT-CAE-001")
        run = CAERun.objects.get(study=study, run_code="RUN-001")
        result = CAEResult.objects.get(run=run, metric_code="fill_time")
        self.assertEqual(result.value, 1.42)
        self.assertEqual(run.boundary_settings["mold_temperature"], 60)
        self.assertTrue(BulkImportBatch.objects.get(id=batch_id).reconciliation["balanced"])

    def test_cae_template_is_versioned(self):
        response = self.client.get("/api/v1/import-templates/cae_results")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Schema-Version"], "1.0")
        self.assertIn("metric_code", response.content.decode())
