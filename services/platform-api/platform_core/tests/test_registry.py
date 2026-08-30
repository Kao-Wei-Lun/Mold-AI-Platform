from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, override_settings

from platform_core.identity import ensure_account_profile
from platform_core.models import (
    AccessRole,
    Artifact,
    AuditEvent,
    DataScope,
    Mold,
    MoldRevision,
    ProductPart,
    Project,
    RoleAssignment,
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
