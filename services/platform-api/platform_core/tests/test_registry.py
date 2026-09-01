from __future__ import annotations

from time import perf_counter

from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from platform_core.identity import ensure_account_profile
from platform_core.models import (
    AccessRole,
    Artifact,
    AuditEvent,
    CAEStudy,
    DataScope,
    Mold,
    MoldPlan,
    MoldRevision,
    ProductPart,
    Project,
    RoleAssignment,
    TrialCase,
)


def account(username: str, role_code: str):
    user = get_user_model().objects.create_user(username=username, password="Registry-Test-2026!")
    ensure_account_profile(user)
    RoleAssignment.objects.create(
        user=user,
        role=AccessRole.objects.get(code=role_code),
        data_scope=DataScope.objects.get(code="public-demo"),
        granted_by=user,
        reason="Registry test setup",
    )
    return user


@override_settings(DEMO_AUTH_MODE="local")
class MoldRegistryApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.engineer = account("registry-engineer", "mold_engineer")
        self.client.force_login(self.engineer)

    def create_hierarchy(self):
        project = self.client.post(
            "/api/v1/registry/projects",
            {"code": "P-001", "name": "Demo program", "reason": "Test project"},
            content_type="application/json",
        )
        self.assertEqual(project.status_code, 201)
        part = self.client.post(
            "/api/v1/registry/parts",
            {
                "project_id": project.json()["id"],
                "part_number": "PART-001",
                "name": "Housing",
                "product_type": "housing",
                "material_code": "ABS-GENERAL",
                "reason": "Test part",
            },
            content_type="application/json",
        )
        self.assertEqual(part.status_code, 201)
        mold = self.client.post(
            "/api/v1/registry/molds",
            {
                "project_id": project.json()["id"],
                "product_part_id": part.json()["id"],
                "mold_code": "MOLD-001",
                "name": "Housing mold",
                "cavity_count": 2,
                "reason": "Test mold",
            },
            content_type="application/json",
        )
        self.assertEqual(mold.status_code, 201)
        revision = self.client.post(
            "/api/v1/registry/revisions",
            {
                "mold_id": mold.json()["id"],
                "revision_code": "A",
                "change_summary": "Initial revision",
                "reason": "Test revision",
            },
            content_type="application/json",
        )
        self.assertEqual(revision.status_code, 201)
        return project.json(), part.json(), mold.json(), revision.json()

    def test_create_hierarchy_and_release_revision(self):
        project, part, mold, revision = self.create_hierarchy()
        self.assertEqual(part["project_id"], project["id"])
        self.assertEqual(mold["product_part_id"], part["id"])

        released = self.client.patch(
            f"/api/v1/registry/revisions/{revision['id']}",
            {"status": "released", "row_version": 1, "reason": "Approved for Demo"},
            content_type="application/json",
        )
        self.assertEqual(released.status_code, 200)
        self.assertEqual(released.json()["status"], "released")
        self.assertIsNotNone(released.json()["released_at"])
        self.assertTrue(
            AuditEvent.objects.filter(event_type="registry.revision.updated.v1").exists()
        )

    def test_engineering_history_is_linked_traceable_and_scope_filtered(self):
        _, _, mold_payload, revision_payload = self.create_hierarchy()
        mold = Mold.objects.get(id=mold_payload["id"])
        revision = MoldRevision.objects.get(id=revision_payload["id"])
        plan = MoldPlan.objects.create(
            plan_code="PLAN-001",
            name="Housing review plan",
            purpose=MoldPlan.Purpose.DESIGN_CHANGE,
            project=mold.project,
            part=mold.product_part,
            mold=mold,
            mold_revision=revision,
            status=MoldPlan.Status.READY,
            owner_id="registry-engineer",
            scope=mold.project.scope,
            classification="public_demo",
            created_by="registry-engineer",
            updated_by="registry-engineer",
        )
        study = CAEStudy.objects.create(
            study_code="CAE-REG-001",
            connector_key="test",
            integration_level="structured_metadata",
            source_record_id="cae-reg-1",
            source_version="1",
            source_hash="a" * 64,
            mapping_version="1",
            solver_name="Moldflow",
            product_ref="PART-001",
            mold_revision_ref="MOLD-001@A",
            material_model_code="ABS-GENERAL",
            mesh_family="3d",
            objective="Check fill balance",
            owner="cae-engineer",
            classification="public_demo",
            acl_scopes=["public-demo"],
        )
        private_study = CAEStudy.objects.create(
            study_code="CAE-PRIVATE-001",
            connector_key="test",
            integration_level="structured_metadata",
            source_record_id="cae-private-1",
            source_version="1",
            source_hash="b" * 64,
            mapping_version="1",
            solver_name="Moldflow",
            product_ref="PART-001",
            mold_revision_ref="MOLD-001@A",
            material_model_code="ABS-GENERAL",
            mesh_family="3d",
            objective="Must not leak",
            owner="private-engineer",
            classification="public_demo",
            acl_scopes=["company-private"],
        )
        trial = TrialCase.objects.create(
            case_code="TRIAL-REG-001",
            connector_key="test",
            source_record_id="trial-reg-1",
            source_version="1",
            source_hash="c" * 64,
            mapping_version="1",
            classification="public_demo",
            acl_scopes=["public-demo"],
            mold_revision_ref="MOLD-001@A",
            part_revision_ref="PART-001@A",
            machine_code="MACHINE-001",
            material_code="ABS-GENERAL",
            product_type="housing",
            purpose="First trial",
            outcome="accepted",
            started_at=timezone.now(),
        )

        response = self.client.get(f"/api/v1/registry/molds/{mold.id}/engineering-history")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        record_ids = {item["record_id"] for item in payload["items"]}
        self.assertTrue({str(plan.id), str(study.id), str(trial.id)}.issubset(record_ids))
        self.assertNotIn(str(private_study.id), record_ids)
        self.assertEqual(payload["counts"]["mold_plan"], 1)
        self.assertTrue(any(node["id"] == str(revision.id) for node in payload["lineage"]["nodes"]))
        self.assertTrue(payload["audit_events"])

        revision_response = self.client.get(
            f"/api/v1/registry/revisions/{revision.id}/engineering-history"
        )
        self.assertEqual(revision_response.status_code, 200)
        self.assertEqual(revision_response.json()["subject"]["revision_id"], str(revision.id))

    def test_new_release_supersedes_previous_release(self):
        _, _, mold, first = self.create_hierarchy()
        self.client.patch(
            f"/api/v1/registry/revisions/{first['id']}",
            {"status": "released", "row_version": 1, "reason": "Release A"},
            content_type="application/json",
        )
        second = self.client.post(
            "/api/v1/registry/revisions",
            {
                "mold_id": mold["id"],
                "revision_code": "B",
                "reason": "Create B",
            },
            content_type="application/json",
        ).json()
        self.client.patch(
            f"/api/v1/registry/revisions/{second['id']}",
            {"status": "released", "row_version": 1, "reason": "Release B"},
            content_type="application/json",
        )
        self.assertEqual(MoldRevision.objects.get(id=first["id"]).status, "superseded")

    def test_governed_revision_actions_create_release_supersede_and_archive(self):
        _, _, mold, first = self.create_hierarchy()
        self.client.post(
            f"/api/v1/registry/revisions/{first['id']}/actions",
            {"action": "release", "row_version": 1, "reason": "Release baseline"},
            content_type="application/json",
        )

        created = self.client.post(
            f"/api/v1/registry/molds/{mold['id']}/revisions",
            {"change_summary": "Next governed design", "reason": "Start next version"},
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["revision_code"], "B")
        self.assertEqual(created.json()["source_revision_id"], first["id"])

        released = self.client.post(
            f"/api/v1/registry/revisions/{created.json()['id']}/actions",
            {"action": "release", "row_version": 1, "reason": "Approve new design"},
            content_type="application/json",
        )
        self.assertEqual(released.status_code, 200)
        self.assertEqual(released.json()["status"], "released")
        self.assertEqual(released.json()["superseded_revision_id"], first["id"])
        self.assertEqual(released.json()["warnings"][0]["code"], "RELEASED_WITHOUT_CAD")
        self.assertEqual(MoldRevision.objects.get(id=first["id"]).status, "superseded")

        immutable = self.client.patch(
            f"/api/v1/registry/revisions/{created.json()['id']}",
            {
                "change_summary": "Rewrite released history",
                "row_version": 2,
                "reason": "Must be rejected",
            },
            content_type="application/json",
        )
        self.assertEqual(immutable.status_code, 409)
        self.assertEqual(immutable.json()["error"]["code"], "RELEASED_REVISION_IMMUTABLE")

        current_archive = self.client.post(
            f"/api/v1/registry/revisions/{created.json()['id']}/actions",
            {"action": "archive", "row_version": 2, "reason": "Must be rejected"},
            content_type="application/json",
        )
        self.assertEqual(current_archive.status_code, 409)
        self.assertEqual(current_archive.json()["error"]["code"], "INVALID_LIFECYCLE_TRANSITION")

        archived = self.client.post(
            f"/api/v1/registry/revisions/{first['id']}/actions",
            {"action": "archive", "row_version": 3, "reason": "Archive superseded baseline"},
            content_type="application/json",
        )
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(archived.json()["status"], "archived")

    def test_mold_impact_and_lifecycle_actions_enforce_state_and_row_version(self):
        _, _, mold, revision = self.create_hierarchy()
        preview = self.client.get(f"/api/v1/registry/molds/{mold['id']}/impact-preview")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["impact"]["draft_revisions"], 1)
        self.assertIn("retire", preview.json()["allowed_actions"])

        stale = self.client.post(
            f"/api/v1/registry/molds/{mold['id']}/actions",
            {"action": "retire", "row_version": 999, "reason": "Stale request"},
            content_type="application/json",
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"]["code"], "VERSION_CONFLICT")

        retired = self.client.post(
            f"/api/v1/registry/molds/{mold['id']}/actions",
            {"action": "retire", "row_version": 1, "reason": "End new planning"},
            content_type="application/json",
        )
        self.assertEqual(retired.status_code, 200)
        self.assertEqual(retired.json()["status"], "retired")
        self.assertEqual(retired.json()["impact"]["draft_revisions"], 1)

        invalid = self.client.post(
            f"/api/v1/registry/molds/{mold['id']}/revisions",
            {"revision_code": "B", "reason": "Must fail while retired"},
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)

        reactivated = self.client.post(
            f"/api/v1/registry/molds/{mold['id']}/actions",
            {"action": "reactivate", "row_version": 2, "reason": "Resume governed work"},
            content_type="application/json",
        )
        self.assertEqual(reactivated.status_code, 200)
        self.assertEqual(reactivated.json()["status"], "active")
        event = AuditEvent.objects.get(event_type="registry.mold.reactivate.v1")
        self.assertIn(f"mold:{mold['id']}", event.target_refs)
        self.assertTrue(MoldRevision.objects.filter(id=revision["id"]).exists())

    def test_mold_discovery_filters_tree_and_overview_are_governed(self):
        project, part, mold, revision = self.create_hierarchy()

        searched = self.client.get(
            "/api/v1/registry/molds",
            {
                "q": "PART-001",
                "project_id": project["id"],
                "part_id": part["id"],
                "mold_type": "injection",
                "status": "active",
                "revision_status": "draft",
                "has_cad": "false",
                "view": "tree",
                "sort": "-updated_at",
                "page": 1,
                "page_size": 25,
            },
        )

        self.assertEqual(searched.status_code, 200)
        self.assertEqual(searched.json()["page"]["total"], 1)
        self.assertEqual(searched.json()["items"][0]["id"], mold["id"])
        self.assertEqual(searched.json()["items"][0]["current_revision_code"], None)
        self.assertEqual(searched.json()["items"][0]["artifact_count"], 0)
        self.assertEqual(searched.json()["items"][0]["revisions"][0]["id"], revision["id"])

        overview = self.client.get("/api/v1/registry/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertGreaterEqual(overview.json()["counts"]["active_projects"], 1)
        self.assertGreaterEqual(overview.json()["counts"]["active_molds"], 1)
        self.assertGreaterEqual(overview.json()["counts"]["draft_revisions"], 1)

        Artifact.objects.create(
            name="Discovery CAD",
            kind=Artifact.Kind.CAD_SOURCE,
            dataset_id="manual-cad-upload-v1",
            mold_revision_id=revision["id"],
        )
        with_cad = self.client.get("/api/v1/registry/molds", {"has_cad": "true"})
        self.assertEqual(with_cad.status_code, 200)
        self.assertEqual(with_cad.json()["page"]["total"], 1)
        self.assertEqual(with_cad.json()["items"][0]["artifact_count"], 1)

    def test_mold_discovery_keeps_the_ten_thousand_row_demo_budget(self):
        scope = DataScope.objects.get(code="public-demo")
        project = Project.objects.create(scope=scope, code="PERF-PROJECT", name="Performance")
        Mold.objects.bulk_create(
            [
                Mold(
                    project=project,
                    mold_code=f"PERF-MOLD-{index:05d}",
                    name=f"Performance mold {index}",
                    mold_type="injection",
                )
                for index in range(10_000)
            ],
            batch_size=1_000,
        )

        started = perf_counter()
        response = self.client.get(
            "/api/v1/registry/molds",
            {"project_id": str(project.id), "page": 1, "page_size": 25},
        )
        elapsed_ms = (perf_counter() - started) * 1_000

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["page"]["total"], 10_000)
        self.assertEqual(len(response.json()["items"]), 25)
        self.assertLess(elapsed_ms, 1_500, f"registry discovery took {elapsed_ms:.1f} ms")

    def test_codes_are_unique_and_immutable(self):
        project, _, mold, _ = self.create_hierarchy()
        duplicate = self.client.post(
            "/api/v1/registry/molds",
            {
                "project_id": project["id"],
                "mold_code": mold["mold_code"],
                "name": "Duplicate",
                "reason": "Conflict check",
            },
            content_type="application/json",
        )
        self.assertEqual(duplicate.status_code, 409)
        renamed = self.client.patch(
            f"/api/v1/registry/molds/{mold['id']}",
            {"mold_code": "RENAMED", "row_version": 1, "reason": "Must fail"},
            content_type="application/json",
        )
        self.assertEqual(renamed.status_code, 409)

    def test_mold_type_must_be_an_active_governed_choice(self):
        project = self.client.post(
            "/api/v1/registry/projects",
            {"code": "P-TYPE", "name": "Type governance", "reason": "Test project"},
            content_type="application/json",
        ).json()
        invalid = self.client.post(
            "/api/v1/registry/molds",
            {
                "project_id": project["id"],
                "mold_code": "MOLD-FREE-TEXT",
                "name": "Invalid mold",
                "mold_type": "whatever-the-user-types",
                "reason": "Verify controlled value",
            },
            content_type="application/json",
        )
        valid = self.client.post(
            "/api/v1/registry/molds",
            {
                "project_id": project["id"],
                "mold_code": "MOLD-3PLATE",
                "name": "Three plate mold",
                "mold_type": "three_plate",
                "reason": "Verify controlled value",
            },
            content_type="application/json",
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["error"]["code"], "VALIDATION_MOLD_TYPE")
        self.assertEqual(valid.status_code, 201)
        self.assertEqual(valid.json()["mold_type"], "three_plate")

    def test_part_detail_supports_read_and_controlled_update(self):
        _, part, _, _ = self.create_hierarchy()
        detail = self.client.get(f"/api/v1/registry/parts/{part['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["part_number"], "PART-001")
        self.assertEqual(len(detail.json()["molds"]), 1)

        updated = self.client.patch(
            f"/api/v1/registry/parts/{part['id']}",
            {
                "name": "Updated housing",
                "row_version": 1,
                "reason": "Correct governed display name",
            },
            content_type="application/json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Updated housing")
        immutable = self.client.patch(
            f"/api/v1/registry/parts/{part['id']}",
            {
                "part_number": "RENAMED",
                "row_version": 2,
                "reason": "Must fail",
            },
            content_type="application/json",
        )
        self.assertEqual(immutable.status_code, 409)

    def test_stable_detail_contracts_return_related_data_and_hide_missing_records(self):
        project, part, mold, revision = self.create_hierarchy()

        project_detail = self.client.get(f"/api/v1/registry/projects/{project['id']}")
        part_detail = self.client.get(f"/api/v1/registry/parts/{part['id']}")
        mold_detail = self.client.get(f"/api/v1/registry/molds/{mold['id']}")
        revision_detail = self.client.get(f"/api/v1/registry/revisions/{revision['id']}")

        self.assertEqual(project_detail.status_code, 200)
        self.assertEqual(part_detail.json()["molds"][0]["id"], mold["id"])
        self.assertEqual(mold_detail.json()["revisions"][0]["id"], revision["id"])
        self.assertEqual(revision_detail.json()["artifacts"], [])
        self.assertEqual(
            self.client.get(
                "/api/v1/registry/molds/00000000-0000-0000-0000-000000000000"
            ).status_code,
            404,
        )

        no_access = get_user_model().objects.create_user(
            username="registry-no-access", password="Registry-No-Access-2026!"
        )
        ensure_account_profile(no_access)
        self.client.force_login(no_access)
        self.assertEqual(
            self.client.get(f"/api/v1/registry/molds/{mold['id']}").status_code,
            403,
        )

    def test_artifact_can_be_linked_and_archived_without_hard_delete(self):
        _, _, _, revision = self.create_hierarchy()
        artifact = Artifact.objects.create(
            name="Governed CAD",
            kind=Artifact.Kind.CAD_SOURCE,
            dataset_id="manual-cad-upload-v1",
        )
        linked = self.client.patch(
            f"/api/v1/registry/artifacts/{artifact.id}",
            {
                "mold_revision_id": revision["id"],
                "quality_status": "validated",
                "row_version": 1,
                "reason": "Attach to revision",
            },
            content_type="application/json",
        )
        self.assertEqual(linked.status_code, 200)
        self.assertEqual(linked.json()["mold_revision_id"], revision["id"])
        archived = self.client.patch(
            f"/api/v1/registry/artifacts/{artifact.id}",
            {"lifecycle_status": "archived", "row_version": 2, "reason": "Retain but hide"},
            content_type="application/json",
        )
        self.assertEqual(archived.status_code, 200)
        self.assertTrue(Artifact.objects.filter(id=artifact.id).exists())

        conflict = self.client.patch(
            f"/api/v1/registry/artifacts/{artifact.id}",
            {"name": "Stale update", "row_version": 2, "reason": "Verify conflict"},
            content_type="application/json",
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["code"], "CONCURRENT_MODIFICATION")

    def test_viewer_cannot_manage_registry(self):
        viewer = account("registry-viewer", "viewer")
        self.client.force_login(viewer)
        self.assertEqual(self.client.get("/api/v1/registry/projects").status_code, 200)
        denied = self.client.post(
            "/api/v1/registry/projects",
            {"code": "DENIED", "name": "Denied", "reason": "Permission test"},
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)

    def test_registry_relationships_are_protected(self):
        project, part, mold, revision = self.create_hierarchy()
        with self.assertRaises(ProtectedError):
            Project.objects.get(id=project["id"]).delete()
        self.assertTrue(ProductPart.objects.filter(id=part["id"]).exists())
        self.assertTrue(Mold.objects.filter(id=mold["id"]).exists())
        self.assertTrue(MoldRevision.objects.filter(id=revision["id"]).exists())
