from django.test import TestCase, override_settings

from platform_core.models import (
    Artifact,
    ArtifactVersion,
    CADCrossModalProfile,
    CADModel,
    FeatureSet,
    Job,
    SimilarityFeedback,
    SimilarityProfile,
    SimilaritySearch,
)
from platform_core.similarity_feedback import compare_cross_modal, fuse_cross_modal


class SimilarityFeedbackTests(TestCase):
    def _feature(self, name: str, suffix: str) -> FeatureSet:
        artifact = Artifact.objects.create(
            name=name,
            kind=Artifact.Kind.CAD_SOURCE,
            product_type="housing",
            material_code="ABS",
        )
        version = ArtifactVersion.objects.create(
            artifact=artifact,
            version_number=1,
            original_filename=f"{name}.stl",
            media_type="model/stl",
            format="stl",
            size_bytes=1,
            sha256=suffix * 64,
            storage_key=f"tests/feedback-{name}.stl",
        )
        cad = CADModel.objects.create(
            artifact_version=version,
            geometry_status=CADModel.GeometryStatus.SUCCEEDED,
        )
        return FeatureSet.objects.create(
            cad_model=cad,
            schema_version="1.0",
            extractor_version=f"feedback-{suffix}",
            vector=[1.0] + [0.0] * 11,
            vector_dimension=12,
            vector_checksum=suffix * 64,
            index_collection="test",
            index_version="feedback-v1",
            index_status=FeatureSet.IndexStatus.INDEXED,
        )

    def _search(self) -> tuple[SimilaritySearch, FeatureSet]:
        query = self._feature("query", "a")
        candidate = self._feature("candidate", "b")
        profile = SimilarityProfile.objects.create(
            profile_key="feedback-test",
            weights={"geometry": 1.0},
            candidate_collection="test",
            index_version="feedback-v1",
        )
        job = Job.objects.create(
            capability_id="mold.similarity_search",
            capability_version="1.0",
            state=Job.State.SUCCEEDED,
            queue="cad",
            resource_class="vector",
            input_artifact_version=query.cad_model.artifact_version,
        )
        search = SimilaritySearch.objects.create(
            job=job,
            query_feature_set=query,
            profile=profile,
            result={
                "results": [
                    {
                        "artifact_version_id": str(candidate.cad_model.artifact_version_id),
                        "overall_score": 0.9,
                    }
                ]
            },
        )
        return search, candidate

    def test_manual_engineering_profile_requires_optimistic_row_version(self) -> None:
        feature = self._feature("profile", "c")
        url = (
            f"/api/v1/artifact-versions/{feature.cad_model.artifact_version_id}"
            "/similarity-engineering-profile"
        )
        first = self.client.put(
            url,
            {
                "tolerance_strictness": "precision",
                "ctq_count": 12,
                "flow_length_ratio": 80,
                "projected_area": 4200,
                "clamp_force_band": "150-200t",
                "gate_type": "hot_runner",
            },
            content_type="application/json",
        )
        stale = self.client.put(
            url,
            {"tolerance_strictness": "standard", "ctq_count": 2, "row_version": 99},
            content_type="application/json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["profile"]["row_version"], 1)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"]["code"], "CONFLICT_ROW_VERSION")

    def test_cross_modal_scores_are_only_fused_when_both_profiles_exist(self) -> None:
        query = self._feature("fusion-query", "d")
        candidate = self._feature("fusion-candidate", "e")
        for feature in (query, candidate):
            CADCrossModalProfile.objects.create(
                artifact_version=feature.cad_model.artifact_version,
                tolerance_strictness="precision",
                ctq_count=10,
                flow_length_ratio=90,
                projected_area=3000,
                clamp_force_band="150-200t",
                gate_type="hot_runner",
                updated_by="tester",
            )
        cross = compare_cross_modal(
            query.cad_model.artifact_version, candidate.cad_model.artifact_version
        )
        base = {
            "overall_score": 0.8,
            "effective_weights": {"geometry": 1.0},
            "sub_scores": {"geometry": 0.8},
            "feature_availability": {"geometry": True},
            "similarities": [],
        }

        fused = fuse_cross_modal(base, cross)

        self.assertEqual(cross["tolerance"], 1.0)
        self.assertEqual(cross["cae"], 1.0)
        self.assertEqual(fused["overall_score"], 0.83)
        self.assertAlmostEqual(sum(fused["effective_weights"].values()), 1.0)
        self.assertEqual(fused["fusion_contract"], "manual-ctq-cae@1.0")

    @override_settings(SIMILARITY_FEEDBACK_RETENTION_DAYS=90)
    def test_negative_feedback_requires_reason_and_replays_idempotently(self) -> None:
        search, candidate = self._search()
        url = f"/api/v1/similarity-searches/{search.id}/feedback"
        payload = {
            "candidate_artifact_version_id": str(candidate.cad_model.artifact_version_id),
            "action": "not_relevant",
            "idempotency_key": "feedback-1",
        }
        rejected = self.client.post(url, payload, content_type="application/json")
        payload["reason_code"] = "different_function"
        first = self.client.post(url, payload, content_type="application/json")
        second = self.client.post(url, payload, content_type="application/json")

        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.json()["error"]["code"], "VALIDATION_FEEDBACK_REASON")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.json()["created"])
        self.assertFalse(second.json()["created"])
        self.assertEqual(SimilarityFeedback.objects.count(), 1)

    def test_candidate_outside_authorized_result_cannot_receive_feedback(self) -> None:
        search, _ = self._search()
        outsider = self._feature("outsider", "f")

        response = self.client.post(
            f"/api/v1/similarity-searches/{search.id}/feedback",
            {
                "candidate_artifact_version_id": str(outsider.cad_model.artifact_version_id),
                "action": "accept_reference",
                "idempotency_key": "feedback-outside",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "SIMILARITY_CANDIDATE_NOT_AUTHORIZED")
