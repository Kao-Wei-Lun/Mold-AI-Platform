from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from platform_core.assistant_providers import ProviderGeneration, ProviderHealth
from platform_core.ingestion import create_upload_records
from platform_core.models import AuditEvent, CADModel, FeatureSet, Job
from platform_core.similarity import create_similarity_records, extract_feature_set
from platform_core.tasks import process_cad_job

from .fixtures import ASCII_TETRAHEDRON_STL


@override_settings(SIMILARITY_AUTO_INDEX=False)
class AssistantTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    def create_completed_search(self):
        upload = SimpleUploadedFile(
            "assistant-query.stl", ASCII_TETRAHEDRON_STL, content_type="model/stl"
        )
        upload_records = create_upload_records(
            upload, artifact_name="Assistant Query", dataset_id="public-demo-v1"
        )
        process_cad_job.run(str(upload_records.job.id))
        cad_model = CADModel.objects.get(artifact_version=upload_records.version)
        feature = extract_feature_set(cad_model)
        feature.index_status = FeatureSet.IndexStatus.INDEXED
        feature.save(update_fields=["index_status"])
        records = create_similarity_records(upload_records.version, top_k=5, filters={})
        candidate_id = "bb2ffb64-4fa4-4708-9b1b-a5d64bdd2240"
        records.search.result = {
            "schema_version": "1.0",
            "search_id": str(records.search.id),
            "results": [
                {
                    "rank": 1,
                    "artifact_version_id": candidate_id,
                    "artifact_name": "Reference A",
                    "overall_score": 0.928,
                    "sub_scores": {
                        "geometry": 0.962,
                        "dimension": 0.941,
                        "topology": 0.918,
                        "metadata": 1.0,
                    },
                    "similarities": [
                        {
                            "message": "Overall proportions are close.",
                            "evidence_ref": "feature:a:geometry",
                        }
                    ],
                    "differences": [
                        {
                            "message": "The right-side rib group differs.",
                            "evidence_ref": "feature:a:topology",
                        }
                    ],
                }
            ],
            "limitations": ["Visual embedding is not included."],
        }
        records.search.save(update_fields=["result"])
        records.job.state = Job.State.SUCCEEDED
        records.job.stage = "completed"
        records.job.progress = 100
        records.job.save(update_fields=["state", "stage", "progress"])
        return records, candidate_id

    def test_contextual_question_resolves_selected_similarity_candidate(self) -> None:
        records, candidate_id = self.create_completed_search()

        response = self.client.post(
            "/api/v1/assistant/messages",
            {
                "message": "為什麼這個排第一？",
                "context": {
                    "context_version": "1.0",
                    "page": "similarity_search",
                    "query_artifact_version_id": str(
                        records.search.query_feature_set.cad_model.artifact_version_id
                    ),
                    "similarity_search_id": str(records.search.id),
                    "selected_candidate_artifact_version_id": candidate_id,
                    "job_id": str(records.job.id),
                    "ui_locale": "zh-TW",
                },
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("ranked #1", payload["answer"]["summary"])
        self.assertIn("geometry: 96.2%", payload["answer"]["facts"][0])
        self.assertEqual(payload["tool_calls"][0]["name"], "get_similarity_explanation")
        self.assertEqual(payload["ui_actions"][0]["type"], "assistant.show_evidence")
        self.assertFalse(payload["provider"]["llm_available"])
        self.assertEqual(AuditEvent.objects.count(), 1)

    def test_context_rejects_unknown_fields_and_bad_versions(self) -> None:
        unknown = self.client.post(
            "/api/v1/assistant/messages",
            {"message": "help", "context": {"page": "engineering_workspace", "tenant": "x"}},
            content_type="application/json",
        )
        unsupported = self.client.post(
            "/api/v1/assistant/messages",
            {
                "message": "help",
                "context": {"context_version": "9.0", "page": "engineering_workspace"},
            },
            content_type="application/json",
        )

        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(unknown.json()["error"]["code"], "VALIDATION_ASSISTANT_CONTEXT")
        self.assertEqual(unsupported.status_code, 400)
        self.assertEqual(unsupported.json()["error"]["code"], "VALIDATION_CONTEXT_VERSION")

    def test_capability_endpoint_discloses_provider_degradation(self) -> None:
        response = self.client.get("/api/v1/assistant/capabilities")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"]["status"], "degraded")
        self.assertEqual(response.json()["ui_action_protocol_version"], "1.0")
        self.assertEqual(
            response.json()["supported_intents"][:5],
            [
                "explain_similarity",
                "explain_design_review",
                "summarize_knowledge",
                "summarize_process_cases",
                "explain_cae_comparison",
            ],
        )

    def test_openai_generation_replaces_language_but_keeps_domain_tool_result(self) -> None:
        records, candidate_id = self.create_completed_search()
        generated_answer = {
            "summary": "Grounded provider explanation for the persisted 92.8% result.",
            "facts": ["The persisted geometry lane is 96.2%."],
            "interpretation": ["Available lanes support the persisted rank."],
            "recommendations": ["Review the persisted geometric differences."],
            "uncertainties": ["Visual embedding is not included."],
            "evidence_refs": [f"similarity-search:{records.search.id}"],
        }

        class FakeProvider:
            def health(self):
                return ProviderHealth("openai-responses", "openai", True, "ok", None)

            def generate(self, envelope):
                self.envelope = envelope
                return ProviderGeneration(
                    status="succeeded",
                    provider="openai-responses",
                    mode="openai",
                    reason=None,
                    answer=generated_answer,
                    latency_ms=12,
                    usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                    provider_profile="openai-demo-public-v1",
                    model="configured-test-model",
                    prompt_profile="mold-assistant-grounded-v1",
                    data_policy_version="public-demo-minimized-v1",
                    request_id="req-test",
                )

        fake = FakeProvider()
        with patch("platform_core.assistant.get_assistant_provider", return_value=fake):
            response = self.client.post(
                "/api/v1/assistant/messages",
                {
                    "message": "Explain the selected result",
                    "context": {
                        "page": "similarity_search",
                        "similarity_search_id": str(records.search.id),
                        "selected_candidate_artifact_version_id": candidate_id,
                    },
                },
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"]["mode"], "openai")
        self.assertEqual(payload["answer"], generated_answer)
        self.assertEqual(
            payload["tool_calls"][0]["result_ref"], f"similarity-search:{records.search.id}"
        )
        self.assertEqual(fake.envelope.intent, "explain_similarity")
        self.assertEqual(fake.envelope.evidence[0]["classification"], "public_demo")

    def test_provider_failure_preserves_deterministic_engineering_answer(self) -> None:
        records, candidate_id = self.create_completed_search()

        class FailingProvider:
            def health(self):
                return ProviderHealth("openai-responses", "openai", True, "ok", None)

            def generate(self, envelope):
                return ProviderGeneration(
                    status="failed",
                    provider="openai-responses",
                    mode="deterministic_fallback",
                    reason="OPENAI_RATE_LIMITED",
                    answer=None,
                    latency_ms=4,
                    usage={"input_tokens": None, "output_tokens": None, "total_tokens": None},
                    provider_profile="openai-demo-public-v1",
                    model="configured-test-model",
                    prompt_profile="mold-assistant-grounded-v1",
                    data_policy_version="public-demo-minimized-v1",
                )

        with patch(
            "platform_core.assistant.get_assistant_provider", return_value=FailingProvider()
        ):
            response = self.client.post(
                "/api/v1/assistant/messages",
                {
                    "message": "Explain the selected result",
                    "context": {
                        "page": "similarity_search",
                        "similarity_search_id": str(records.search.id),
                        "selected_candidate_artifact_version_id": candidate_id,
                    },
                },
                content_type="application/json",
            )

        payload = response.json()
        self.assertEqual(payload["provider"]["reason"], "OPENAI_RATE_LIMITED")
        self.assertEqual(payload["provider"]["mode"], "deterministic_fallback")
        self.assertIn("92.8%", payload["answer"]["summary"])
