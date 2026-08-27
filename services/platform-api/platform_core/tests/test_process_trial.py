from django.test import TestCase

from platform_core.models import (
    AuditEvent,
    CorrectiveAction,
    DefectObservation,
    ProcessCaseSearch,
    ProcessParameter,
    ProcessRun,
    TrialCase,
)
from platform_core.process_connectors import (
    SyntheticProcessTrialConnector,
    seed_demo_process_trials,
)
from platform_core.process_trial import SCORING_PROFILE_VERSION, search_process_cases


class ProcessTrialTests(TestCase):
    def setUp(self) -> None:
        self.seed = seed_demo_process_trials()

    def compatible_query(self) -> dict[str, object]:
        return {
            "defect_code": "short_shot",
            "material_code": "PA6-GF30",
            "machine_code": "IM-180T",
            "product_type": "connector_housing",
            "location": "far_flow_end",
            "parameters": {
                "injection_pressure_mpa": {"value": 84, "unit": "MPa"},
                "injection_speed_mm_s": {"value": 43, "unit": "mm/s"},
                "melt_temperature_c": {"value": 279, "unit": "degC"},
            },
            "top_k": 5,
        }

    def test_connector_contract_seeds_canonical_graph_idempotently(self) -> None:
        connector = SyntheticProcessTrialConnector()
        replay = seed_demo_process_trials(connector)

        self.assertEqual(connector.health()["status"], "ok")
        self.assertEqual(len(connector.discover()), 6)
        self.assertEqual(self.seed.created, 6)
        self.assertEqual(replay.created, 0)
        self.assertEqual(replay.existing, 6)
        self.assertEqual(TrialCase.objects.count(), 6)
        self.assertEqual(ProcessRun.objects.count(), 6)
        self.assertGreaterEqual(ProcessParameter.objects.count(), 36)
        self.assertEqual(DefectObservation.objects.count(), 6)
        self.assertEqual(CorrectiveAction.objects.count(), 6)
        trial = TrialCase.objects.get(case_code="TRIAL-DEMO-001")
        self.assertEqual(trial.classification, "public_demo")
        self.assertEqual(trial.acl_scopes, ["public-demo"])
        self.assertEqual(len(trial.source_hash), 64)
        self.assertTrue(trial.data_quality["not_production_ground_truth"])

    def test_fixture_and_trial_case_endpoints_expose_provenance(self) -> None:
        fixture_status = self.client.get("/api/v1/process-trial/demo-fixtures")
        fixture_replay = self.client.post(
            "/api/v1/process-trial/demo-fixtures", {}, content_type="application/json"
        )
        cases = self.client.get("/api/v1/trial-cases")

        self.assertEqual(fixture_status.status_code, 200)
        self.assertEqual(fixture_status.json()["connector"]["source_type"], "synthetic")
        self.assertEqual(fixture_replay.status_code, 200)
        self.assertEqual(fixture_replay.json()["existing"], 6)
        self.assertEqual(cases.status_code, 200)
        self.assertEqual(len(cases.json()["items"]), 6)
        first = cases.json()["items"][0]
        detail = self.client.get(f"/api/v1/trial-cases/{first['trial_case_id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["provenance"]["source_type"], "synthetic")
        self.assertEqual(
            detail.json()["runs"][0]["parameters"]["injection_pressure_mpa"]["unit"], "MPa"
        )
        self.assertTrue(detail.json()["runs"][0]["corrective_actions"][0]["evidence_refs"])

    def test_search_ranks_cases_and_returns_only_controlled_evidence_based_steps(self) -> None:
        response = self.client.post(
            "/api/v1/process-case-searches",
            self.compatible_query(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["abstained"])
        self.assertEqual(payload["scoring_profile_version"], SCORING_PROFILE_VERSION)
        self.assertEqual(payload["results"][0]["case_code"], "TRIAL-DEMO-001")
        self.assertEqual(payload["results"][0]["score_breakdown"]["defect"], 1.0)
        self.assertEqual(payload["results"][0]["score_breakdown"]["material"], 1.0)
        self.assertTrue(payload["results"][0]["similarities"])
        self.assertTrue(payload["results"][0]["evidence_refs"])
        self.assertEqual(payload["results"][0]["provenance"]["source_type"], "synthetic")
        steps = payload["recommendation"]["controlled_trial_steps"]
        self.assertEqual(len(steps), 2)
        self.assertTrue(all(step["requires_engineer_approval"] for step in steps))
        self.assertTrue(all(step["do_not_auto_apply"] for step in steps))
        self.assertTrue(all(step["historical_before"] for step in steps))
        self.assertTrue(all(step["historical_after"] for step in steps))
        self.assertTrue(all(step["stop_condition"] for step in steps))
        self.assertIn("synthetic", " ".join(payload["limitations"]).lower())
        self.assertTrue(payload["lineage"]["search_ref"].startswith("process-case-search:"))
        self.assertEqual(ProcessCaseSearch.objects.count(), 1)
        audit = AuditEvent.objects.get(event_type="process.case_search.v1")
        self.assertEqual(audit.detail["result_count"], payload["result_count"])
        self.assertEqual(len(audit.payload_hash), 64)

        assistant = self.client.post(
            "/api/v1/assistant/messages",
            {
                "message": "Summarize the comparable process cases",
                "context": {"page": "process_trial", "process_search_id": payload["search_id"]},
            },
            content_type="application/json",
        )
        self.assertEqual(assistant.status_code, 200)
        self.assertEqual(assistant.json()["tool_calls"][0]["name"], "get_process_case_search")
        self.assertIn("TRIAL-DEMO-001", assistant.json()["answer"]["facts"][0])

        persisted = self.client.get(f"/api/v1/process-case-searches/{payload['search_id']}")
        self.assertEqual(persisted.status_code, 200)
        self.assertEqual(persisted.json(), payload)

    def test_missing_material_abstains_without_retrieving_or_exposing_ranges(self) -> None:
        query = self.compatible_query()
        query["material_code"] = ""
        response = self.client.post(
            "/api/v1/process-case-searches", query, content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["abstained"])
        self.assertEqual(payload["result_count"], 0)
        self.assertEqual(payload["recommendation"]["reason_code"], "MISSING_COMPATIBILITY_CONTEXT")
        self.assertEqual(payload["recommendation"]["required_fields"], ["material_code"])
        self.assertEqual(payload["recommendation"]["controlled_trial_steps"], [])

    def test_machine_mismatch_and_unsuccessful_case_do_not_produce_ranges(self) -> None:
        mismatch = self.compatible_query()
        mismatch["machine_code"] = "IM-120T"
        mismatch_response = self.client.post(
            "/api/v1/process-case-searches", mismatch, content_type="application/json"
        )
        negative = {
            **self.compatible_query(),
            "material_code": "ABS-GENERAL",
            "machine_code": "IM-120T",
        }
        negative_response = self.client.post(
            "/api/v1/process-case-searches", negative, content_type="application/json"
        )

        self.assertTrue(mismatch_response.json()["recommendation"]["abstained"])
        self.assertEqual(
            mismatch_response.json()["recommendation"]["reason_code"],
            "NO_COMPATIBLE_SUCCESSFUL_CASE",
        )
        self.assertEqual(negative_response.json()["results"][0]["case_code"], "TRIAL-DEMO-006")
        self.assertTrue(negative_response.json()["recommendation"]["abstained"])
        self.assertEqual(negative_response.json()["recommendation"]["controlled_trial_steps"], [])

    def test_out_of_bound_input_returns_blocking_finding_and_abstains(self) -> None:
        query = self.compatible_query()
        query["parameters"] = {"injection_pressure_mpa": {"value": 400, "unit": "MPa"}}
        search = search_process_cases(query)

        self.assertTrue(search.abstained)
        self.assertEqual(search.result["rule_findings"][0]["severity"], "blocking")
        self.assertEqual(
            search.result["recommendation"]["reason_code"],
            "INPUT_OUTSIDE_DEMO_VALIDATION_BOUND",
        )
        self.assertEqual(search.result["recommendation"]["controlled_trial_steps"], [])

    def test_invalid_defect_parameter_unit_and_top_k_are_rejected(self) -> None:
        invalid_defect = self.client.post(
            "/api/v1/process-case-searches",
            {"defect_code": "unknown", "material_code": "PA6-GF30"},
            content_type="application/json",
        )
        invalid_unit_query = self.compatible_query()
        invalid_unit_query["parameters"] = {"injection_pressure_mpa": {"value": 80, "unit": "psi"}}
        invalid_unit = self.client.post(
            "/api/v1/process-case-searches",
            invalid_unit_query,
            content_type="application/json",
        )
        invalid_top_k = self.client.post(
            "/api/v1/process-case-searches",
            {**self.compatible_query(), "top_k": 11},
            content_type="application/json",
        )

        self.assertEqual(invalid_defect.status_code, 400)
        self.assertEqual(invalid_defect.json()["error"]["code"], "VALIDATION_DEFECT_CODE")
        self.assertEqual(invalid_unit.status_code, 400)
        self.assertEqual(invalid_unit.json()["error"]["code"], "VALIDATION_PARAMETER_UNIT")
        self.assertEqual(invalid_top_k.status_code, 400)
        self.assertEqual(invalid_top_k.json()["error"]["code"], "VALIDATION_TOP_K")

    def test_non_demo_acl_case_is_hidden_from_list_and_detail(self) -> None:
        trial = TrialCase.objects.get(case_code="TRIAL-DEMO-001")
        trial.classification = "company_confidential"
        trial.acl_scopes = ["company-private"]
        trial.save(update_fields=["classification", "acl_scopes"])

        cases = self.client.get("/api/v1/trial-cases")
        detail = self.client.get(f"/api/v1/trial-cases/{trial.id}")

        self.assertEqual(len(cases.json()["items"]), 5)
        self.assertEqual(detail.status_code, 404)
