from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings

from platform_core.identity import audit_identity_event, ensure_account_profile
from platform_core.models import (
    AccessRole,
    Artifact,
    ArtifactVersion,
    AuditEvent,
    DataScope,
    HistoryRecordState,
    Job,
    JobEvent,
    KnowledgeSearch,
    LineageEdge,
    RoleAssignment,
)


def account(username: str, role_code: str):
    user = get_user_model().objects.create_user(username=username, password="History-Test-2026!")
    ensure_account_profile(user)
    RoleAssignment.objects.create(
        user=user,
        role=AccessRole.objects.get(code=role_code),
        data_scope=DataScope.objects.get(code="public-demo"),
        granted_by=user,
        reason="History center test setup",
    )
    return user


def artifact_version(name: str, version_number: int = 1) -> ArtifactVersion:
    artifact = Artifact.objects.create(
        name=name,
        kind=Artifact.Kind.CAD_SOURCE,
        dataset_id="public-demo-v1",
        created_by="history-test",
    )
    return ArtifactVersion.objects.create(
        artifact=artifact,
        version_number=version_number,
        original_filename=f"{name}.stl",
        media_type="model/stl",
        format="stl",
        size_bytes=12,
        sha256=(name.lower().replace("-", "0") + "0" * 64)[:64],
        storage_key=f"tests/history/{name}-{version_number}.stl",
        malware_status=ArtifactVersion.MalwareStatus.BASIC_SCREENED,
    )


@override_settings(DEMO_AUTH_MODE="local")
class HistoryCentersTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = account("history-admin", "platform_admin")
        self.client.force_login(self.admin)
        self.source = artifact_version("history-source")

    def create_job(self, *, state: str = Job.State.QUEUED, capability: str = "cad.parse"):
        job = Job.objects.create(
            capability_id=capability,
            state=state,
            input_artifact_version=self.source,
            input_snapshot={"dataset_id": "public-demo-v1"},
            error_code="TEST_FAILURE" if state == Job.State.FAILED else "",
        )
        JobEvent.objects.create(
            job=job,
            from_state="",
            to_state=state,
            stage=state,
            progress=0,
            detail={"source": "test"},
        )
        return job

    def test_job_center_lists_timeline_and_requests_cancel(self):
        job = self.create_job()

        listing = self.client.get("/api/v1/history/jobs?page=1&page_size=10")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["page"]["total"], 1)

        detail = self.client.get(f"/api/v1/history/jobs/{job.id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.json()["events"]), 1)

        cancelled = self.client.post(
            f"/api/v1/history/jobs/{job.id}",
            data=json.dumps({"action": "cancel", "reason": "Operator requested stop"}),
            content_type="application/json",
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["state"], Job.State.CANCEL_REQUESTED)
        self.assertEqual(cancelled.json()["events"][-1]["to_state"], Job.State.CANCEL_REQUESTED)
        self.assertTrue(AuditEvent.objects.filter(event_type="job.cancel_requested.v1").exists())

    @patch("platform_core.history_views.process_cad_job.apply_async")
    def test_failed_supported_job_can_be_retried(self, apply_async):
        job = self.create_job(state=Job.State.FAILED)
        response = self.client.post(
            f"/api/v1/history/jobs/{job.id}",
            data=json.dumps({"action": "retry", "reason": "Corrected transient input issue"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["state"], Job.State.QUEUED)
        self.assertEqual(response.json()["input_snapshot"]["retry_of_job_id"], str(job.id))
        apply_async.assert_called_once()

    def test_analysis_detail_can_be_archived_and_stale_write_is_rejected(self):
        search = KnowledgeSearch.objects.create(
            query="draft angle",
            principal_scopes=["public-demo"],
            filters={"dataset_ids": ["public-demo-v1"]},
            retrieval_config={"top_k": 5},
            result={"results": [{"title": "Demo rule"}]},
        )

        listing = self.client.get("/api/v1/history/analyses?analysis_type=knowledge_search")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["page"]["total"], 1)

        archived = self.client.post(
            f"/api/v1/history/analyses/knowledge_search/{search.id}",
            data=json.dumps(
                {"action": "archive", "row_version": 1, "reason": "Superseded test result"}
            ),
            content_type="application/json",
        )
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(archived.json()["lifecycle"]["status"], "archived")
        self.assertEqual(
            HistoryRecordState.objects.get(record_id=search.id).archive_reason,
            "Superseded test result",
        )

        stale = self.client.post(
            f"/api/v1/history/analyses/knowledge_search/{search.id}",
            data=json.dumps({"action": "restore", "row_version": 1, "reason": "Stale restore"}),
            content_type="application/json",
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"]["code"], "CONCURRENT_MODIFICATION")

    def test_audit_center_redacts_secrets_exports_and_is_read_only(self):
        event = audit_identity_event(
            "history.tested.v1",
            actor_id="history-admin",
            target_refs=["artifact:demo"],
            detail={"api_key": "do-not-return", "profile_key": "mold-profile"},
        )
        listing = self.client.get("/api/v1/history/audit-events?event_type=history.tested")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["items"][0]["detail"]["api_key"], "[REDACTED]")
        self.assertEqual(listing.json()["items"][0]["detail"]["profile_key"], "mold-profile")

        detail = self.client.get(f"/api/v1/history/audit-events/{event.id}")
        self.assertEqual(detail.status_code, 200)
        exported = self.client.get("/api/v1/history/audit-events/export?event_type=history.tested")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("text/csv", exported["Content-Type"])
        self.assertNotIn("do-not-return", exported.content.decode("utf-8"))
        self.assertEqual(
            self.client.patch(
                f"/api/v1/history/audit-events/{event.id}",
                data=json.dumps({"detail": {}}),
                content_type="application/json",
            ).status_code,
            405,
        )

        event.detail = {"changed": True}
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()

    def test_lineage_center_returns_normalized_graph(self):
        output = artifact_version("history-output")
        job = self.create_job(state=Job.State.SUCCEEDED)
        LineageEdge.objects.create(
            from_artifact_version=self.source,
            to_artifact_version=output,
            relationship=LineageEdge.Relationship.DERIVED_FROM,
            job=job,
        )

        response = self.client.get(
            f"/api/v1/history/lineage?root_type=artifact_version&root_id={self.source.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["schema_version"], "history-lineage-v1")
        self.assertGreaterEqual(len(response.json()["nodes"]), 3)
        self.assertEqual(
            {edge["relation"] for edge in response.json()["edges"]},
            {"derived_from", "produced"},
        )

    def test_job_events_are_append_only(self):
        event = self.create_job().events.get()
        event.detail = {"changed": True}
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
