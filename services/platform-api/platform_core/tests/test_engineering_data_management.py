from __future__ import annotations

from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from platform_core.hmi import create_demo_hmi_png
from platform_core.identity import ensure_account_profile
from platform_core.models import (
    AccessRole,
    DataScope,
    HMICorrectionDecision,
    HMIProfileVersion,
    MasterDataMappingBacklog,
    Mold,
    MoldRevision,
    Project,
    RoleAssignment,
    TrialCase,
    TrialCorrectionRecord,
)


def account(username: str, role_code: str):
    user = get_user_model().objects.create_user(username=username, password="Phase5-Test-2026!")
    ensure_account_profile(user)
    RoleAssignment.objects.create(
        user=user,
        role=AccessRole.objects.get(code=role_code),
        data_scope=DataScope.objects.get(code="public-demo"),
        granted_by=user,
        reason="Phase 5 test setup",
    )
    return user


@override_settings(DEMO_AUTH_MODE="local")
class EngineeringDataManagementTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.engineer = account("phase5-engineer", "mold_engineer")
        self.client.force_login(self.engineer)
        scope = DataScope.objects.get(code="public-demo")
        project = Project.objects.create(scope=scope, code="PHASE5", name="Phase 5")
        mold = Mold.objects.create(project=project, mold_code="M-PHASE5", name="Phase 5 mold")
        self.revision = MoldRevision.objects.create(
            mold=mold, revision_code="A", status=MoldRevision.Status.RELEASED
        )
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    def create_trial(self):
        return self.client.post(
            "/api/v1/trial-cases",
            {
                "case_code": "TRIAL-MANAGED-001",
                "mold_revision_id": str(self.revision.id),
                "machine_code": "IM-120T",
                "material_code": "ABS-GENERAL",
                "product_type": "housing",
                "purpose": "Initial qualification",
                "outcome": "pending",
                "started_at": "2026-08-29T01:00:00Z",
                "reason": "Create governed trial",
            },
            content_type="application/json",
        )

    def test_trial_close_blocks_overwrite_and_correction_preserves_source(self) -> None:
        created = self.create_trial()
        self.assertEqual(created.status_code, 201)
        trial = created.json()
        self.assertEqual(trial["lifecycle_status"], "draft")

        closed = self.client.patch(
            f"/api/v1/trial-cases/{trial['trial_case_id']}",
            {"action": "close", "row_version": 1, "reason": "Trial accepted"},
            content_type="application/json",
        )
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json()["lifecycle_status"], "closed")

        overwrite = self.client.patch(
            f"/api/v1/trial-cases/{trial['trial_case_id']}",
            {
                "action": "update",
                "row_version": 2,
                "purpose": "Silent overwrite",
                "reason": "Must fail",
            },
            content_type="application/json",
        )
        self.assertEqual(overwrite.status_code, 409)
        self.assertEqual(overwrite.json()["error"]["code"], "TRIAL_IMMUTABLE_AFTER_CLOSE")

        corrected = self.client.patch(
            f"/api/v1/trial-cases/{trial['trial_case_id']}",
            {
                "action": "correct",
                "row_version": 2,
                "changes": {"purpose": "Qualified with corrected note"},
                "reason": "Correct transcription without changing source",
            },
            content_type="application/json",
        )
        self.assertEqual(corrected.status_code, 200)
        self.assertEqual(corrected.json()["purpose"], "Initial qualification")
        self.assertEqual(len(corrected.json()["corrections"]), 1)
        self.assertEqual(TrialCorrectionRecord.objects.count(), 1)

        reopened = self.client.patch(
            f"/api/v1/trial-cases/{trial['trial_case_id']}",
            {"action": "reopen", "row_version": 3, "reason": "Additional sampling"},
            content_type="application/json",
        )
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["lifecycle_status"], "reopened")

    def test_structured_cae_run_import_and_archive_lifecycle(self) -> None:
        created = self.client.post(
            "/api/v1/cae-studies",
            {
                "study_code": "CAE-MANAGED-001",
                "solver_name": "Moldflow",
                "mold_revision_ref": "M-PHASE5@A",
                "material_model_code": "ABS-GENERAL",
                "mesh_family": "3d-tetra",
                "objective": "Compare pressure",
                "reason": "Create structured study",
            },
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        study = created.json()
        imported = self.client.post(
            f"/api/v1/cae-studies/{study['study_id']}/runs",
            {
                "run_code": "RUN-001",
                "solver_version": "2026",
                "mesh_checksum": "a" * 64,
                "boundary_settings": {"gate": "center"},
                "results": [
                    {"metric_code": "fill_time_s", "value": 1.2, "unit": "s"},
                    {
                        "metric_code": "max_injection_pressure_mpa",
                        "value": 88.4,
                        "unit": "MPa",
                    },
                ],
                "reason": "Import parsed solver results",
            },
            content_type="application/json",
        )
        self.assertEqual(imported.status_code, 201)
        self.assertEqual(len(imported.json()["runs"][0]["results"]), 2)

        archived = self.client.patch(
            f"/api/v1/cae-studies/{study['study_id']}",
            {"action": "archive", "row_version": 1, "reason": "Retain superseded study"},
            content_type="application/json",
        )
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(archived.json()["lifecycle_status"], "archived")
        blocked = self.client.post(
            f"/api/v1/cae-studies/{study['study_id']}/runs",
            {"run_code": "RUN-002", "results": [], "reason": "Must fail"},
            content_type="application/json",
        )
        self.assertEqual(blocked.status_code, 404)

    def test_hmi_profile_version_and_human_correction_are_traceable(self) -> None:
        profiles = self.client.get("/api/v1/hmi-profiles")
        self.assertEqual(profiles.status_code, 200)
        published = next(item for item in profiles.json()["items"] if item["status"] == "published")
        cloned = self.client.post(
            "/api/v1/hmi-profiles",
            {
                "source_profile_id": published["profile_id"],
                "version": "1.1",
                "change_summary": "Phase 5 governed clone",
                "reason": "Prepare next profile",
            },
            content_type="application/json",
        )
        self.assertEqual(cloned.status_code, 201)
        promoted = self.client.post(
            f"/api/v1/hmi-profiles/{cloned.json()['profile_id']}/actions",
            {"action": "publish", "reason": "Approve version for future extraction"},
            content_type="application/json",
        )
        self.assertEqual(promoted.status_code, 200)
        self.assertEqual(promoted.json()["status"], "published")
        self.assertEqual(
            HMIProfileVersion.objects.get(id=published["profile_id"]).status,
            HMIProfileVersion.Status.RETIRED,
        )

        upload = SimpleUploadedFile(
            "phase5-hmi.png", create_demo_hmi_png(), content_type="image/png"
        )
        extraction = self.client.post(
            "/api/v1/hmi-extractions",
            {"file": upload, "profile": "demo-generic-injection@1.1"},
        )
        self.assertEqual(extraction.status_code, 201)
        extraction_fields = extraction.json()["fields"]
        field = next(item for item in extraction_fields if item["review_status"] == "needs_review")
        reviewed = self.client.post(
            f"/api/v1/hmi-extractions/{extraction.json()['extraction_id']}/review",
            {
                "reviewed_by": "phase5-engineer",
                "fields": [
                    {
                        "field_id": field["field_id"],
                        "action": "correct",
                        "value": 56,
                        "unit": "MPa",
                        "reason": "Screen glare caused OCR ambiguity",
                    }
                ],
            },
            content_type="application/json",
        )
        self.assertEqual(reviewed.status_code, 200)
        reviewed_fields = reviewed.json()["fields"]
        reviewed_field = next(
            item for item in reviewed_fields if item["field_id"] == field["field_id"]
        )
        self.assertEqual(reviewed_field["raw_text"], field["raw_text"])
        self.assertEqual(reviewed_field["effective_value"], 56)
        self.assertEqual(len(reviewed_field["correction_decisions"]), 1)
        self.assertEqual(HMICorrectionDecision.objects.count(), 1)

    def test_viewer_can_read_but_cannot_mutate_engineering_data(self) -> None:
        viewer = account("phase5-viewer", "viewer")
        self.client.force_login(viewer)
        self.assertEqual(self.client.get("/api/v1/trial-cases").status_code, 200)
        denied = self.create_trial()
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["code"], "PERMISSION_SCOPE_REQUIRED")
        self.assertEqual(TrialCase.objects.filter(case_code="TRIAL-MANAGED-001").count(), 0)

    def test_unknown_canonical_value_is_rejected_and_added_to_mapping_backlog(self) -> None:
        response = self.client.post(
            "/api/v1/trial-cases",
            {
                "case_code": "TRIAL-UNKNOWN-MACHINE",
                "mold_revision_id": str(self.revision.id),
                "machine_code": "UNKNOWN-9000",
                "material_code": "ABS-GENERAL",
                "product_type": "housing",
                "started_at": "2026-08-29T01:00:00Z",
                "reason": "Verify mapping backlog",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "MASTER_DATA_MAPPING_REQUIRED")
        backlog = MasterDataMappingBacklog.objects.get(raw_value="UNKNOWN-9000")
        self.assertEqual(backlog.target_kind, "machine")
        self.assertEqual(backlog.status, MasterDataMappingBacklog.Status.PENDING)
