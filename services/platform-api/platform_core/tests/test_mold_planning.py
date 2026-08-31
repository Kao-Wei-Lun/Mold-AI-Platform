from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from platform_core.design_review import get_demo_rule_profile
from platform_core.ingestion import create_upload_records
from platform_core.models import (
    Artifact,
    DataScope,
    Mold,
    MoldPlanHandoff,
    MoldPlanRequirement,
    MoldPlanResolution,
    MoldRevision,
    ProductPart,
    Project,
)
from platform_core.tasks import process_cad_job
from platform_core.tests.fixtures import ASCII_TETRAHEDRON_STL


@override_settings(DEMO_AUTH_MODE="local", SIMILARITY_AUTO_INDEX=False)
class MoldPlanningPersistenceTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        scope = DataScope.objects.get(code="public-demo")
        project = Project.objects.create(scope=scope, code="PLAN-PROJECT", name="Plan project")
        part = ProductPart.objects.create(
            project=project,
            part_number="PLAN-PART",
            name="Plan part",
            product_type="housing",
            material_code="ABS-GENERAL",
        )
        mold = Mold.objects.create(
            project=project,
            product_part=part,
            mold_code="PLAN-MOLD",
            name="Plan mold",
            mold_type="three_plate",
        )
        self.revision = MoldRevision.objects.create(
            mold=mold, revision_code="A", status=MoldRevision.Status.RELEASED
        )
        records = create_upload_records(
            SimpleUploadedFile("plan.stl", ASCII_TETRAHEDRON_STL, content_type="model/stl"),
            artifact_name="Planning CAD",
        )
        process_cad_job.run(str(records.job.id))
        Artifact.objects.filter(pk=records.artifact.pk).update(
            mold_revision=self.revision,
            product_type="housing",
            material_code="ABS-GENERAL",
        )
        self.version = records.version
        self.profile = get_demo_rule_profile()
        self.admin = get_user_model().objects.create_superuser(
            username="mold-plan-admin",
            email="mold-plan@example.test",
            password="Mold-Plan-2026!",
        )
        self.client.force_login(self.admin)

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    def body(self) -> dict[str, object]:
        return {
            "name": "Housing mold planning",
            "purpose": "new_mold",
            "mold_revision_id": str(self.revision.id),
            "cad_artifact_version_id": str(self.version.id),
            "context": {"molding_process": "injection"},
        }

    def create_plan(self) -> dict[str, object]:
        response = self.client.post(
            "/api/v1/mold-plans", self.body(), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_create_resolve_list_and_reopen_a_governed_plan(self) -> None:
        created = self.create_plan()
        self.assertEqual(created["status"], "draft")
        self.assertEqual(created["context"]["product_type"]["source_type"], "cad")

        resolved = self.client.post(
            f"/api/v1/mold-plans/{created['plan_id']}/resolve",
            {},
            content_type="application/json",
        )
        self.assertEqual(resolved.status_code, 200, resolved.content)
        current = resolved.json()
        self.assertEqual(current["status"], "ready")
        self.assertEqual(current["latest_resolution"]["selected_profile_id"], str(self.profile.id))
        self.assertEqual(current["latest_resolution"]["resolution_number"], 1)

        listed = self.client.get("/api/v1/mold-plans?status=ready")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["page"]["total"], 1)

        completed = self.client.post(
            f"/api/v1/mold-plans/{created['plan_id']}/actions",
            {
                "action": "complete",
                "row_version": current["row_version"],
                "reason": "Planning approved",
            },
            content_type="application/json",
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["status"], "completed")
        reopened = self.client.post(
            f"/api/v1/mold-plans/{created['plan_id']}/actions",
            {
                "action": "reopen",
                "row_version": completed.json()["row_version"],
                "reason": "Design changed",
            },
            content_type="application/json",
        )
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["status"], "draft")

    def test_draft_update_uses_optimistic_concurrency(self) -> None:
        created = self.create_plan()
        path = f"/api/v1/mold-plans/{created['plan_id']}"
        conflict = self.client.patch(
            path,
            {"name": "Changed name", "row_version": 99},
            content_type="application/json",
        )
        self.assertEqual(conflict.status_code, 409)
        updated = self.client.patch(
            path,
            {"name": "Changed planning name", "row_version": created["row_version"]},
            content_type="application/json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["row_version"], 2)

    def test_resolution_snapshot_is_immutable(self) -> None:
        created = self.create_plan()
        self.client.post(
            f"/api/v1/mold-plans/{created['plan_id']}/resolve",
            {},
            content_type="application/json",
        )
        resolution = MoldPlanResolution.objects.get()
        resolution.reason = "Mutated reason"

        with self.assertRaises(ValidationError):
            resolution.save()

    def test_resolution_creates_requirements_and_design_review_handoff(self) -> None:
        created = self.create_plan()
        resolved = self.client.post(
            f"/api/v1/mold-plans/{created['plan_id']}/resolve",
            {},
            content_type="application/json",
        ).json()
        summary = resolved["latest_resolution"]["requirement_summary"]
        self.assertEqual(summary["total"], self.profile.rules.filter(enabled=True).count())
        self.assertEqual(MoldPlanRequirement.objects.count(), summary["total"])
        self.assertGreater(summary["cad_evidence"], 0)

        with patch("platform_core.mold_planning_views.run_design_review_job.apply_async"):
            response = self.client.post(
                f"/api/v1/mold-plans/{created['plan_id']}/handoffs/design_review",
                {"row_version": resolved["row_version"]},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 201, response.content)
        handoff = response.json()
        self.assertIn("target=design_review", handoff["contract"]["ui_path"])
        self.assertEqual(MoldPlanHandoff.objects.count(), 1)

        review = self.client.get(
            f"/api/v1/design-reviews/{handoff['review_id']}"
        )
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.json()["source_mold_plan"]["plan_id"], created["plan_id"])
        self.assertEqual(
            review.json()["resolution_snapshot"]["mold_plan_resolution_id"],
            resolved["latest_resolution"]["resolution_id"],
        )

        current = self.client.get(f"/api/v1/mold-plans/{created['plan_id']}").json()
        replay = self.client.post(
            f"/api/v1/mold-plans/{created['plan_id']}/handoffs/design_review",
            {"row_version": current["row_version"]},
            content_type="application/json",
        )
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["idempotent_replay"])

    def test_handoff_rejects_a_changed_ruleset(self) -> None:
        created = self.create_plan()
        resolved = self.client.post(
            f"/api/v1/mold-plans/{created['plan_id']}/resolve",
            {},
            content_type="application/json",
        ).json()
        type(self.profile).objects.filter(id=self.profile.id).update(
            ruleset_checksum="f" * 64
        )
        response = self.client.post(
            f"/api/v1/mold-plans/{created['plan_id']}/handoffs/design_review",
            {"row_version": resolved["row_version"]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "MOLD_PLAN_RULESET_MISMATCH")

    def test_handoff_requires_mold_planning_permission(self) -> None:
        created = self.create_plan()
        resolved = self.client.post(
            f"/api/v1/mold-plans/{created['plan_id']}/resolve",
            {},
            content_type="application/json",
        ).json()
        viewer = get_user_model().objects.create_user(
            username="handoff-viewer",
            email="handoff-viewer@example.test",
            password="Handoff-Viewer-2026!",
        )
        self.client.force_login(viewer)
        response = self.client.post(
            f"/api/v1/mold-plans/{created['plan_id']}/handoffs/design_review",
            {"row_version": resolved["row_version"]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn(
            response.json()["error"]["code"],
            {"ACCESS_DENIED", "PERMISSION_SCOPE_REQUIRED"},
        )
