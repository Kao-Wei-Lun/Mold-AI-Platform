from django.test import TestCase

from platform_core.cae import COMPATIBILITY_PROFILE_VERSION, compare_cae_runs
from platform_core.cae_connectors import SyntheticCAEConnector, seed_demo_cae_studies
from platform_core.models import AuditEvent, CAEComparison, CAEResult, CAERun, CAEStudy


class CAETests(TestCase):
    def setUp(self) -> None:
        self.seed = seed_demo_cae_studies()

    def get_run(self, study_code: str) -> CAERun:
        return (
            CAERun.objects.select_related("study")
            .prefetch_related("results")
            .get(study__study_code=study_code)
        )

    def test_connector_seeds_canonical_study_run_result_graph_idempotently(self) -> None:
        connector = SyntheticCAEConnector()
        replay = seed_demo_cae_studies(connector)

        self.assertEqual(connector.health()["status"], "ok")
        self.assertFalse(connector.health()["official_solver_api_connected"])
        self.assertEqual(connector.health()["integration_level"], "synthetic_structured_export")
        self.assertEqual(self.seed.created, 5)
        self.assertEqual(replay.created, 0)
        self.assertEqual(replay.existing, 5)
        self.assertEqual(CAEStudy.objects.count(), 5)
        self.assertEqual(CAERun.objects.count(), 5)
        self.assertEqual(CAEResult.objects.count(), 30)
        study = CAEStudy.objects.get(study_code="CAE-DEMO-BASELINE")
        self.assertEqual(study.classification, "public_demo")
        self.assertEqual(study.acl_scopes, ["public-demo"])
        self.assertEqual(len(study.source_hash), 64)
        self.assertTrue(study.data_quality["not_solver_ground_truth"])
        run = study.runs.get()
        self.assertEqual(len(run.input_hash), 64)
        self.assertEqual(run.results.get(metric_code="fill_time_s").unit, "s")

    def test_fixture_and_study_endpoints_expose_metric_provenance(self) -> None:
        status = self.client.get("/api/v1/cae/demo-fixtures")
        replay = self.client.post("/api/v1/cae/demo-fixtures", {}, content_type="application/json")
        studies = self.client.get("/api/v1/cae-studies")

        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["connector"]["official_solver_api_connected"])
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["existing"], 5)
        self.assertEqual(studies.status_code, 200)
        self.assertEqual(len(studies.json()["items"]), 5)
        baseline = next(
            item for item in studies.json()["items"] if item["study_code"] == "CAE-DEMO-BASELINE"
        )
        detail = self.client.get(f"/api/v1/cae-studies/{baseline['study_id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            detail.json()["provenance"]["integration_level"], "synthetic_structured_export"
        )
        self.assertEqual(len(detail.json()["runs"][0]["results"]), 6)
        result = detail.json()["runs"][0]["results"][0]
        self.assertTrue(result["result_id"])
        self.assertTrue(result["metric_code"])
        self.assertEqual(result["parser"]["version"], "1.0.0")
        self.assertTrue(result["source_locator"]["json_path"].startswith("$.run.results"))
        self.assertEqual(len(result["evidence_refs"]), 4)

    def test_compatible_comparison_calculates_metric_deltas_with_evidence(self) -> None:
        baseline = self.get_run("CAE-DEMO-BASELINE")
        candidate = self.get_run("CAE-DEMO-CANDIDATE")
        response = self.client.post(
            "/api/v1/cae-comparisons",
            {"baseline_run_id": str(baseline.id), "candidate_run_id": str(candidate.id)},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["compatible"])
        self.assertEqual(payload["compatibility_profile_version"], COMPATIBILITY_PROFILE_VERSION)
        self.assertEqual(payload["comparison_summary"]["comparable_metric_count"], 6)
        self.assertEqual(payload["comparison_summary"]["finding_counts"]["improved"], 5)
        self.assertEqual(
            payload["comparison_summary"]["finding_counts"]["changed_review_required"], 1
        )
        pressure = next(
            item
            for item in payload["metric_comparisons"]
            if item["metric_code"] == "max_injection_pressure_mpa"
        )
        self.assertEqual(pressure["baseline"]["value"], 95.0)
        self.assertEqual(pressure["candidate"]["value"], 89.0)
        self.assertEqual(pressure["delta"], -6.0)
        self.assertEqual(pressure["finding"], "improved")
        self.assertEqual(pressure["interpretation_type"], "deterministic_metric_comparison")
        self.assertEqual(len(pressure["evidence_refs"]), 7)
        temperature = next(
            item
            for item in payload["metric_comparisons"]
            if item["metric_code"] == "min_melt_front_temperature_c"
        )
        self.assertEqual(temperature["finding"], "changed_review_required")
        self.assertTrue(payload["lineage"]["comparison_ref"].startswith("cae-comparison:"))
        self.assertIn("synthetic", " ".join(payload["limitations"]).lower())
        self.assertEqual(CAEComparison.objects.count(), 1)
        audit = AuditEvent.objects.get(event_type="cae.comparison_created.v1")
        self.assertTrue(audit.detail["compatible"])
        self.assertEqual(audit.detail["comparable_metric_count"], 6)
        self.assertEqual(len(audit.payload_hash), 64)

        assistant = self.client.post(
            "/api/v1/assistant/messages",
            {
                "message": "Explain this CAE comparison",
                "context": {"page": "cae", "cae_comparison_id": payload["comparison_id"]},
            },
            content_type="application/json",
        )
        self.assertEqual(assistant.status_code, 200)
        self.assertIn("compatible", assistant.json()["answer"]["summary"])
        self.assertEqual(assistant.json()["tool_calls"][0]["name"], "get_cae_comparison")

        detail = self.client.get(f"/api/v1/cae-comparisons/{payload['comparison_id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json(), payload)

    def test_solver_version_material_and_mesh_mismatches_block_all_deltas(self) -> None:
        baseline = self.get_run("CAE-DEMO-BASELINE")
        cases = {
            "CAE-DEMO-INCOMPATIBLE-SOLVER": "CAE_INCOMPATIBLE_SOLVER_VERSION",
            "CAE-DEMO-INCOMPATIBLE-MATERIAL": "CAE_INCOMPATIBLE_MATERIAL_MODEL",
            "CAE-DEMO-INCOMPATIBLE-MESH": "CAE_INCOMPATIBLE_MESH_CHECKSUM",
        }
        for study_code, expected_code in cases.items():
            with self.subTest(study_code=study_code):
                comparison = compare_cae_runs(baseline, self.get_run(study_code))
                self.assertFalse(comparison.compatible)
                self.assertIn(
                    expected_code, [item["code"] for item in comparison.incompatibilities]
                )
                self.assertEqual(comparison.result["metric_comparisons"], [])
                self.assertEqual(
                    comparison.result["comparison_summary"]["comparable_metric_count"], 0
                )

    def test_compatible_subset_excludes_missing_or_schema_mismatched_metrics(self) -> None:
        baseline = self.get_run("CAE-DEMO-BASELINE")
        candidate = self.get_run("CAE-DEMO-CANDIDATE")
        candidate.results.filter(metric_code="air_trap_count").delete()
        candidate.results.filter(metric_code="max_warpage_mm").update(unit="inch")
        candidate = self.get_run("CAE-DEMO-CANDIDATE")

        comparison = compare_cae_runs(baseline, candidate)

        self.assertTrue(comparison.compatible)
        self.assertEqual(comparison.result["comparison_summary"]["comparable_metric_count"], 4)
        self.assertEqual(comparison.result["comparison_summary"]["excluded_metric_count"], 2)
        codes = [item["code"] for item in comparison.result["metric_incompatibilities"]]
        self.assertIn("CAE_METRIC_MISSING", codes)
        self.assertIn("CAE_METRIC_SCHEMA_MISMATCH", codes)

    def test_quality_flags_exclude_metric_from_compatible_subset(self) -> None:
        baseline = self.get_run("CAE-DEMO-BASELINE")
        candidate = self.get_run("CAE-DEMO-CANDIDATE")
        candidate.results.filter(metric_code="fill_time_s").update(
            quality_flags=["parser_value_uncertain"]
        )
        candidate = self.get_run("CAE-DEMO-CANDIDATE")

        comparison = compare_cae_runs(baseline, candidate)

        excluded = comparison.result["metric_incompatibilities"]
        self.assertEqual(comparison.result["comparison_summary"]["comparable_metric_count"], 5)
        self.assertEqual(excluded[0]["code"], "CAE_METRIC_QUALITY_BLOCKED")
        self.assertEqual(excluded[0]["quality_flags"], ["parser_value_uncertain"])

    def test_unsuccessful_run_status_blocks_comparison(self) -> None:
        baseline = self.get_run("CAE-DEMO-BASELINE")
        candidate = self.get_run("CAE-DEMO-CANDIDATE")
        candidate.status = CAERun.Status.FAILED
        candidate.save(update_fields=["status"])

        comparison = compare_cae_runs(baseline, candidate)

        self.assertFalse(comparison.compatible)
        self.assertIn(
            "CAE_INCOMPATIBLE_CANDIDATE_STATUS",
            [item["code"] for item in comparison.incompatibilities],
        )
        self.assertEqual(comparison.result["metric_comparisons"], [])

    def test_invalid_or_identical_run_ids_are_rejected(self) -> None:
        baseline = self.get_run("CAE-DEMO-BASELINE")
        malformed = self.client.post(
            "/api/v1/cae-comparisons",
            {"baseline_run_id": "not-a-uuid", "candidate_run_id": str(baseline.id)},
            content_type="application/json",
        )
        identical = self.client.post(
            "/api/v1/cae-comparisons",
            {"baseline_run_id": str(baseline.id), "candidate_run_id": str(baseline.id)},
            content_type="application/json",
        )

        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json()["error"]["code"], "VALIDATION_CAE_RUN_ID")
        self.assertEqual(identical.status_code, 400)
        self.assertEqual(identical.json()["error"]["code"], "VALIDATION_CAE_DISTINCT_RUNS")

    def test_non_demo_acl_study_is_hidden_from_list_detail_and_comparison(self) -> None:
        private = CAEStudy.objects.get(study_code="CAE-DEMO-CANDIDATE")
        private.classification = "company_confidential"
        private.acl_scopes = ["company-private"]
        private.save(update_fields=["classification", "acl_scopes"])
        baseline = self.get_run("CAE-DEMO-BASELINE")
        candidate = self.get_run("CAE-DEMO-CANDIDATE")

        studies = self.client.get("/api/v1/cae-studies")
        detail = self.client.get(f"/api/v1/cae-studies/{private.id}")
        comparison = self.client.post(
            "/api/v1/cae-comparisons",
            {"baseline_run_id": str(baseline.id), "candidate_run_id": str(candidate.id)},
            content_type="application/json",
        )

        self.assertEqual(len(studies.json()["items"]), 4)
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(comparison.status_code, 404)
