from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from platform_core.design_review import (
    EVALUATORS,
    create_design_review_records,
    get_demo_rule_profile,
)
from platform_core.ingestion import create_upload_records
from platform_core.models import AuditEvent, CADModel, Job, ReviewDecision, ReviewFinding
from platform_core.tasks import process_cad_job, run_design_review_job
from platform_core.tests.fixtures import ASCII_TETRAHEDRON_STL


@override_settings(SIMILARITY_AUTO_INDEX=False)
class DesignReviewTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

        upload = SimpleUploadedFile(
            "review-part.stl", ASCII_TETRAHEDRON_STL, content_type="model/stl"
        )
        records = create_upload_records(upload, artifact_name="Review fixture")
        process_cad_job.run(str(records.job.id))
        self.version = records.version
        self.cad_model = CADModel.objects.get(artifact_version=self.version)
        self.cad_model.cad_format = "step"
        self.cad_model.unit_system = "mm"
        self.cad_model.bounding_box = {"size": {"x": 30.0, "y": 10.0, "z": 5.0}}
        self.cad_model.volume = 6000.0
        self.cad_model.surface_area = 2200.0
        self.cad_model.face_count = 6
        self.cad_model.edge_count = 12
        self.cad_model.surface_type_histogram = {"plane": 6}
        self.cad_model.quality_flags = []
        self.cad_model.save()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    def test_demo_profile_seeds_versioned_rules_using_registered_evaluators(self) -> None:
        profile = get_demo_rule_profile()

        self.assertEqual(profile.rules.filter(enabled=True).count(), 13)
        self.assertEqual(len(profile.ruleset_checksum), 64)
        self.assertEqual(profile.status, "approved_demo")
        for rule in profile.rules.all():
            self.assertIn(rule.evaluator, EVALUATORS)
            self.assertEqual(
                rule.reference["classification"], "synthetic_demo_not_engineering_guidance"
            )

    def test_review_job_persists_pass_fail_and_not_evaluated_evidence(self) -> None:
        records = create_design_review_records(
            self.version,
            context={"nominal_wall_thickness_mm": 2.0, "max_rib_thickness_mm": 1.5},
        )

        result = run_design_review_job.run(str(records.job.id))

        records.review.refresh_from_db()
        records.job.refresh_from_db()
        findings = records.review.findings.select_related("rule_version")
        self.assertEqual(result["state"], Job.State.SUCCEEDED)
        self.assertEqual(records.review.result_summary["total"], 13)
        self.assertGreater(records.review.result_summary["counts"]["PASS"], 0)
        self.assertGreater(records.review.result_summary["counts"]["FAIL"], 0)
        self.assertEqual(records.review.result_summary["counts"]["NOT_EVALUATED"], 1)
        self.assertEqual(records.review.result_summary["decision"], "FAIL")
        rib = findings.get(rule_version__rule_id="DEMO-RIB-RATIO-012")
        self.assertEqual(rib.result, ReviewFinding.Result.FAIL)
        self.assertEqual(rib.actual_value, 0.75)
        self.assertEqual(rib.limit_value, 0.6)
        self.assertEqual(rib.geometry_location["scope"], "context:rib-measurement")
        self.assertIn("USER_SUPPLIED_DEMO_MEASUREMENT", rib.quality_flags)
        draft = findings.get(rule_version__rule_id="DEMO-DRAFT-MIN-013")
        self.assertEqual(draft.result, ReviewFinding.Result.NOT_EVALUATED)
        self.assertIsNone(draft.actual_value)

        assistant = self.client.post(
            "/api/v1/assistant/messages",
            {
                "message": "Explain this design review",
                "context": {
                    "page": "design_review",
                    "review_id": str(records.review.id),
                },
            },
            content_type="application/json",
        )
        self.assertEqual(assistant.status_code, 200)
        self.assertIn("Design review", assistant.json()["answer"]["summary"])
        self.assertEqual(assistant.json()["tool_calls"][0]["name"], "get_design_review")

    def test_missing_local_measurements_are_never_treated_as_pass(self) -> None:
        records = create_design_review_records(self.version)

        run_design_review_job.run(str(records.job.id))

        local_findings = records.review.findings.filter(
            rule_version__rule_id__in=["DEMO-RIB-RATIO-012", "DEMO-DRAFT-MIN-013"]
        )
        self.assertEqual(local_findings.count(), 2)
        self.assertEqual(
            set(local_findings.values_list("result", flat=True)),
            {ReviewFinding.Result.NOT_EVALUATED},
        )

    @patch("platform_core.views.run_design_review_job.apply_async")
    def test_review_endpoint_creates_async_job_and_replays_idempotently(self, apply_async) -> None:
        payload = {
            "cad_artifact_version_id": str(self.version.id),
            "profile": "demo-general-design@1.0",
            "context": {
                "nominal_wall_thickness_mm": 2.0,
                "max_rib_thickness_mm": 1.5,
            },
            "idempotency_key": "design-review-request-1",
        }

        first = self.client.post("/api/v1/design-reviews", payload, content_type="application/json")
        second = self.client.post(
            "/api/v1/design-reviews", payload, content_type="application/json"
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertFalse(first.json()["idempotent_replay"])
        self.assertTrue(second.json()["idempotent_replay"])
        self.assertEqual(first.json()["job_id"], second.json()["job_id"])
        apply_async.assert_called_once_with(args=[first.json()["job_id"]], queue="cad")

    def test_job_and_review_contract_include_rule_evidence_and_lineage_snapshot(self) -> None:
        records = create_design_review_records(
            self.version,
            context={"minimum_draft_angle_deg": 2.0},
        )
        run_design_review_job.run(str(records.job.id))

        job_response = self.client.get(f"/api/v1/jobs/{records.job.id}")
        review_response = self.client.get(f"/api/v1/design-reviews/{records.review.id}")

        self.assertEqual(job_response.status_code, 200)
        payload = job_response.json()["result"]
        self.assertEqual(payload["review_id"], str(records.review.id))
        self.assertEqual(payload["profile"]["rule_count"], 13)
        self.assertEqual(payload["input_snapshot"]["cad_sha256"], self.version.sha256)
        self.assertEqual(payload["resolution_snapshot"]["selection_mode"], "default")
        self.assertEqual(
            payload["resolution_snapshot"]["selected"]["profile_key"],
            "demo-general-design@1.0",
        )
        self.assertEqual(len(payload["resolution_snapshot"]["applicability_checksum"]), 64)
        self.assertEqual(len(payload["findings"]), 13)
        self.assertEqual(review_response.status_code, 200)
        self.assertTrue(review_response.json()["preview"]["download_url"])

    def test_waiver_requires_reason_and_approver_and_writes_immutable_audit(self) -> None:
        records = create_design_review_records(self.version)
        run_design_review_job.run(str(records.job.id))
        finding = records.review.findings.filter(result=ReviewFinding.Result.FAIL).first()
        assert finding is not None

        invalid = self.client.post(
            f"/api/v1/design-reviews/{records.review.id}/findings/{finding.id}/decisions",
            {"decision": "waived", "decided_by": "reviewer-1"},
            content_type="application/json",
        )
        valid = self.client.post(
            f"/api/v1/design-reviews/{records.review.id}/findings/{finding.id}/decisions",
            {
                "decision": "waived",
                "reason": "Approved for the synthetic Demo fixture only.",
                "decided_by": "reviewer-1",
                "approved_by": "approver-1",
            },
            content_type="application/json",
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["error"]["code"], "VALIDATION_DECISION_REASON")
        self.assertEqual(valid.status_code, 201)
        finding.refresh_from_db()
        self.assertEqual(finding.result, ReviewFinding.Result.FAIL)
        self.assertEqual(ReviewDecision.objects.get().decision, "waived")
        event = AuditEvent.objects.get()
        self.assertEqual(event.actor_id, "reviewer-1")
        self.assertEqual(len(event.payload_hash), 64)
        self.assertEqual(event.detail["finding_result_unchanged"], "FAIL")

    def test_rule_catalog_and_context_validation_endpoints(self) -> None:
        catalog = self.client.get("/api/v1/rule-profiles")
        invalid = self.client.post(
            "/api/v1/design-reviews",
            {
                "cad_artifact_version_id": str(self.version.id),
                "context": {"untrusted_expression": "__import__('os')"},
            },
            content_type="application/json",
        )

        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.json()["items"][0]["rule_count"], 13)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["error"]["code"], "VALIDATION_REVIEW_CONTEXT")
