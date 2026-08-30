import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from platform_core.models import AuditEvent
from platform_core.operations import OPERATIONS_CONTRACT_VERSION, release_snapshot_payload


class ReleaseSnapshotTests(TestCase):
    def test_snapshot_is_versioned_and_excludes_secret_values(self) -> None:
        event = AuditEvent.objects.create(
            event_type="release.snapshot.test",
            actor_id="test",
            target_refs=[],
            detail={"safe": True},
            payload_hash="a" * 64,
        )
        payload = release_snapshot_payload()
        serialized = json.dumps(payload)

        self.assertEqual(payload["operations_contract_version"], OPERATIONS_CONTRACT_VERSION)
        self.assertIn("curated_cad", payload["datasets"])
        self.assertIn("ruleset_checksum", payload["profiles"]["design_review"])
        self.assertIn("status", payload["readiness"])
        self.assertEqual(payload["job_recovery"]["counts"]["total"], 0)
        self.assertIn("environment_files", payload["excluded_sensitive_material"])
        self.assertEqual(payload["records"]["audit_events"], 1)
        self.assertEqual(len(payload["records"]["audit_manifest_sha256"]), 64)
        self.assertEqual(len(payload["records"]["artifact_manifest_sha256"]), 64)
        self.assertNotIn(str(event.id), serialized)
        for forbidden in (
            "OPENAI_API_KEY",
            "DEMO_API_TOKEN",
            "CONTROL_PLANE_API_KEY",
            "DJANGO_SECRET_KEY",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_management_command_emits_valid_json(self) -> None:
        output = StringIO()
        call_command("demo_release_snapshot", "--json", stdout=output)
        payload = json.loads(output.getvalue())

        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["database"]["vendor"], "sqlite")
