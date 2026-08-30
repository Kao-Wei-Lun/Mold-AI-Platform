from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from platform_core.identity import ensure_account_profile
from platform_core.models import (
    AccessRole,
    Artifact,
    AuditEvent,
    DataScope,
    MasterDataItem,
    RoleAssignment,
)


def account(username: str, role_code: str):
    user = get_user_model().objects.create_user(
        username=username, password="Master-Data-Test-2026!"
    )
    ensure_account_profile(user)
    RoleAssignment.objects.create(
        user=user,
        role=AccessRole.objects.get(code=role_code),
        data_scope=DataScope.objects.get(code="public-demo"),
        granted_by=user,
        reason="Master-data test setup",
    )
    return user


@override_settings(DEMO_AUTH_MODE="local")
class MasterDataApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.steward = account("steward", "data_steward")
        self.client.force_login(self.steward)

    def test_seed_is_idempotent_and_options_are_grouped(self):
        before = MasterDataItem.objects.count()
        call_command("seed_master_data")
        call_command("seed_master_data")
        self.assertEqual(MasterDataItem.objects.count(), before)

        response = self.client.get("/api/v1/master-data/options")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()["results"]),
            {
                "dataset",
                "product_type",
                "material",
                "machine",
                "defect",
                "location",
                "unit",
                "mold_type",
                "molding_process",
                "rule_category",
            },
        )
        self.assertTrue(response.json()["results"]["material"][0]["name_zh_tw"])
        self.assertEqual(len(response.json()["results"]["mold_type"]), 8)
        self.assertEqual(
            response.json()["results"]["mold_type"][0]["attributes"]["process_family"],
            "injection",
        )

    def test_create_list_update_etag_and_archive(self):
        created = self.client.post(
            "/api/v1/master-data",
            {
                "kind": "material",
                "code": "POM-DEMO",
                "name_en": "Demo POM",
                "name_zh_tw": "Demo 聚甲醛",
                "attributes": {"family": "POM"},
                "reason": "Add approved Demo material",
            },
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        item = created.json()
        etag = created.headers["ETag"]
        self.assertTrue(AuditEvent.objects.filter(event_type="master_data.created.v1").exists())

        listed = self.client.get("/api/v1/master-data?kind=material&search=POM&page_size=5")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["pagination"]["total"], 1)

        updated = self.client.patch(
            f"/api/v1/master-data/{item['id']}",
            {"name_en": "Engineering POM", "reason": "Clarify display name"},
            content_type="application/json",
            HTTP_IF_MATCH=etag,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["code"], "POM-DEMO")
        self.assertEqual(updated.json()["row_version"], 2)

        stale = self.client.patch(
            f"/api/v1/master-data/{item['id']}",
            {"name_en": "Stale overwrite", "reason": "Should fail"},
            content_type="application/json",
            HTTP_IF_MATCH=etag,
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"]["code"], "CONCURRENT_MODIFICATION")

        immutable = self.client.patch(
            f"/api/v1/master-data/{item['id']}",
            {"code": "POM-CHANGED", "row_version": 2, "reason": "Try rename"},
            content_type="application/json",
        )
        self.assertEqual(immutable.status_code, 409)

        archived = self.client.delete(
            f"/api/v1/master-data/{item['id']}",
            {"row_version": 2, "reason": "No longer approved"},
            content_type="application/json",
        )
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(archived.json()["status"], "archived")
        option_codes = {
            option["code"]
            for option in self.client.get("/api/v1/master-data/options").json()["results"][
                "material"
            ]
        }
        self.assertNotIn("POM-DEMO", option_codes)

    def test_duplicate_code_reference_summary_and_viewer_read_only(self):
        duplicate = self.client.post(
            "/api/v1/master-data",
            {
                "kind": "material",
                "code": "pa6-gf30",
                "name_en": "Duplicate",
                "name_zh_tw": "重複",
                "reason": "Duplicate test",
            },
            content_type="application/json",
        )
        self.assertEqual(duplicate.status_code, 409)

        Artifact.objects.create(name="Referenced", kind="cad_source", material_code="PA6-GF30")
        item = MasterDataItem.objects.get(kind="material", code="PA6-GF30")
        detail = self.client.get(f"/api/v1/master-data/{item.id}")
        self.assertEqual(detail.json()["references"], {"artifacts": 1})

        viewer_client = Client()
        viewer_client.force_login(account("master-reader", "viewer"))
        self.assertEqual(viewer_client.get("/api/v1/master-data/options").status_code, 200)
        denied = viewer_client.post(
            "/api/v1/master-data",
            {
                "kind": "unit",
                "code": "kg",
                "name_en": "Kilogram",
                "name_zh_tw": "公斤",
                "reason": "Permission test",
            },
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)
