from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from platform_core.identity import ensure_account_profile
from platform_core.models import (
    AccessRole,
    Artifact,
    DataScope,
    MasterDataItem,
    Project,
    RoleAssignment,
)


def account(username: str, scopes: list[DataScope]):
    user = get_user_model().objects.create_user(username=username, password="Enterprise-Test-2026!")
    ensure_account_profile(user)
    role = AccessRole.objects.get(code="platform_admin")
    for scope in scopes:
        RoleAssignment.objects.create(
            user=user,
            role=role,
            data_scope=scope,
            granted_by=user,
            reason="Enterprise history test setup",
        )
    return user


@override_settings(DEMO_AUTH_MODE="local")
class EnterpriseHistoryTests(TestCase):
    def setUp(self):
        self.public_scope = DataScope.objects.get(code="public-demo")
        self.company_scope = DataScope.objects.create(
            code="company-alpha",
            name="Company Alpha",
            classification="company_confidential",
        )
        self.client = Client()
        self.admin = account("enterprise-admin", [self.public_scope, self.company_scope])
        self.client.force_login(self.admin)

    def test_policy_enforces_connector_scope_and_isolated_namespaces(self):
        public = self.client.get("/api/v1/enterprise/policy?scope=public-demo")
        self.assertEqual(public.status_code, 200)
        self.assertFalse(public.json()["isolation"]["cross_scope_queries"])

        mismatch = self.client.patch(
            "/api/v1/enterprise/policy",
            data=json.dumps(
                {
                    "scope": "public-demo",
                    "row_version": public.json()["row_version"],
                    "connector_mode": "company",
                    "reason": "Invalid switch test",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(mismatch.status_code, 409)
        self.assertEqual(mismatch.json()["error"]["code"], "CONNECTOR_SCOPE_MISMATCH")

        company = self.client.get("/api/v1/enterprise/policy?scope=company-alpha")
        self.assertEqual(company.status_code, 200)
        self.assertEqual(company.json()["connector_mode"], "company")
        self.assertNotEqual(
            public.json()["isolation"]["index_namespace"],
            company.json()["isolation"]["index_namespace"],
        )

    def test_bulk_import_runs_validation_then_commit_with_reconciliation(self):
        payload = {
            "scope": "company-alpha",
            "domain": "master_data",
            "source_name": "company-materials.csv",
            "idempotency_key": "company-materials-2026-08-29",
            "field_mapping": {"kind": "type", "code": "material_id", "name_en": "label"},
            "records": [{"type": "material", "material_id": "COMP-ABS-1", "label": "Company ABS"}],
        }
        validated = self.client.post(
            "/api/v1/enterprise/import-batches",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(validated.status_code, 201)
        self.assertTrue(validated.json()["validation"]["valid"])
        self.assertFalse(
            MasterDataItem.objects.filter(scope=self.company_scope, code="COMP-ABS-1").exists()
        )

        committed = self.client.post(
            f"/api/v1/enterprise/import-batches/{validated.json()['batch_id']}",
            data=json.dumps({"action": "commit", "reason": "Approved mapping and dry run"}),
            content_type="application/json",
        )
        self.assertEqual(committed.status_code, 200)
        self.assertTrue(committed.json()["reconciliation"]["balanced"])
        self.assertEqual(committed.json()["reconciliation"]["created_count"], 1)
        self.assertTrue(
            MasterDataItem.objects.filter(scope=self.company_scope, code="COMP-ABS-1").exists()
        )

        replay = self.client.post(
            "/api/v1/enterprise/import-batches",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["batch_id"], validated.json()["batch_id"])

    def test_invalid_batch_is_not_committable(self):
        invalid = self.client.post(
            "/api/v1/enterprise/import-batches",
            data=json.dumps(
                {
                    "scope": "public-demo",
                    "domain": "projects",
                    "source_name": "bad.csv",
                    "idempotency_key": "bad-project-batch",
                    "records": [{"code": "MISSING-NAME"}],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 201)
        self.assertFalse(invalid.json()["validation"]["valid"])
        commit = self.client.post(
            f"/api/v1/enterprise/import-batches/{invalid.json()['batch_id']}",
            data=json.dumps({"action": "commit", "reason": "Must fail"}),
            content_type="application/json",
        )
        self.assertEqual(commit.status_code, 409)

    def test_legal_hold_blocks_bulk_archive_after_dry_run(self):
        artifact = Artifact.objects.create(
            name="held-cad",
            kind=Artifact.Kind.CAD_SOURCE,
            classification="company_confidential",
            dataset_id="company-alpha-cad",
        )
        company = self.client.get("/api/v1/enterprise/policy?scope=company-alpha").json()
        updated = self.client.patch(
            "/api/v1/enterprise/policy",
            data=json.dumps(
                {
                    "scope": "company-alpha",
                    "row_version": company["row_version"],
                    "legal_hold": True,
                    "legal_hold_reason": "Active litigation hold",
                    "reason": "Legal approved hold",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()["export_allowed"])

        dry_run = self.client.post(
            "/api/v1/enterprise/bulk-archive",
            data=json.dumps(
                {
                    "scope": "company-alpha",
                    "domain": "artifacts",
                    "record_ids": [str(artifact.id)],
                    "dry_run": True,
                    "reason": "Retention candidate review",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(dry_run.status_code, 201)
        self.assertEqual(dry_run.json()["result"]["would_archive_count"], 0)

        commit = self.client.post(
            "/api/v1/enterprise/bulk-archive",
            data=json.dumps(
                {
                    "scope": "company-alpha",
                    "domain": "artifacts",
                    "record_ids": [str(artifact.id)],
                    "dry_run": False,
                    "reason": "Retention archive",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(commit.status_code, 409)
        artifact.refresh_from_db()
        self.assertEqual(artifact.lifecycle_status, "active")
        audit_export = self.client.get("/api/v1/history/audit-events/export?scope=company-alpha")
        self.assertEqual(audit_export.status_code, 409)
        self.assertEqual(audit_export.json()["error"]["code"], "DLP_EXPORT_BLOCKED")

    def test_scope_without_assignment_is_hidden(self):
        public_only = Client()
        public_only.force_login(account("public-only", [self.public_scope]))
        response = public_only.get("/api/v1/enterprise/policy?scope=company-alpha")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "DATA_SCOPE_DENIED")

    def test_registry_list_is_scope_isolated_sorted_and_paginated(self):
        for index in range(12):
            Project.objects.create(
                scope=self.public_scope,
                code=f"PUBLIC-{index:02d}",
                name=f"Public project {index}",
            )
        Project.objects.create(
            scope=self.company_scope,
            code="COMPANY-SECRET",
            name="Company secret project",
            classification="company_confidential",
        )
        public_only = Client()
        public_only.force_login(account("paginated-public", [self.public_scope]))

        response = public_only.get(
            "/api/v1/registry/projects?q=PUBLIC&page=2&page_size=5&sort=-code"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["page"]["total"], 12)
        self.assertEqual(len(response.json()["items"]), 5)
        self.assertEqual(response.json()["items"][0]["code"], "PUBLIC-06")
        self.assertNotContains(response, "COMPANY-SECRET")

        invalid_sort = public_only.get("/api/v1/registry/projects?sort=unsafe_field")
        self.assertEqual(invalid_sort.status_code, 400)
