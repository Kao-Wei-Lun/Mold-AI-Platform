from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from platform_core.cad_similarity_v2 import extract_feature_set_v2
from platform_core.ingestion import create_upload_records
from platform_core.models import CADModel, FeatureSet, Job, SimilaritySearch
from platform_core.similarity import (
    compare_feature_sets,
    create_similarity_records,
    extract_and_index_cad_model,
    extract_feature_set,
    get_demo_profile,
    index_feature_set,
)
from platform_core.tasks import process_cad_job, run_similarity_job
from platform_core.vector_store import VectorCandidate


def tetrahedron(scale: float) -> bytes:
    return f"""solid tetrahedron
facet normal 0 0 -1
outer loop
vertex 0 0 0
vertex 0 {scale} 0
vertex {scale} 0 0
endloop
endfacet
facet normal 0 -1 0
outer loop
vertex 0 0 0
vertex {scale} 0 0
vertex 0 0 {scale}
endloop
endfacet
facet normal -1 0 0
outer loop
vertex 0 0 0
vertex 0 0 {scale}
vertex 0 {scale} 0
endloop
endfacet
facet normal 1 1 1
outer loop
vertex {scale} 0 0
vertex 0 {scale} 0
vertex 0 0 {scale}
endloop
endfacet
endsolid tetrahedron
""".encode()


@override_settings(SIMILARITY_AUTO_INDEX=False)
class SimilarityTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    def create_feature(
        self,
        name: str,
        scale: float,
        *,
        product_type: str = "housing",
        material_code: str = "PC_ABS",
        dataset_id: str = "similarity-test-v1",
    ) -> FeatureSet:
        upload = SimpleUploadedFile(f"{name}.stl", tetrahedron(scale), content_type="model/stl")
        records = create_upload_records(
            upload,
            artifact_name=name,
            dataset_id=dataset_id,
            product_type=product_type,
            material_code=material_code,
        )
        process_cad_job.run(str(records.job.id))
        cad_model = CADModel.objects.get(artifact_version=records.version)
        feature_set = extract_feature_set(cad_model)
        feature_set.index_status = FeatureSet.IndexStatus.INDEXED
        feature_set.save(update_fields=["index_status"])
        return feature_set

    @patch("platform_core.similarity.upsert_feature")
    def test_extract_and_index_persists_versioned_vector_contract(self, upsert_feature) -> None:
        feature_set = self.create_feature("query", 10)
        feature_set.index_status = FeatureSet.IndexStatus.PENDING
        feature_set.save(update_fields=["index_status"])

        indexed = index_feature_set(feature_set)

        self.assertEqual(indexed.vector_dimension, 12)
        self.assertEqual(len(indexed.vector), 12)
        self.assertEqual(indexed.schema_version, "1.0")
        self.assertEqual(indexed.index_status, FeatureSet.IndexStatus.INDEXED)
        upsert_feature.assert_called_once()

    @override_settings(
        SIMILARITY_INDEX_READ_VERSION="v2",
        SIMILARITY_V2_SHADOW_INDEX=False,
    )
    @patch("platform_core.cad_similarity_v2.extract_and_index_cad_model_v2")
    @patch("platform_core.similarity.index_feature_set")
    @patch("platform_core.similarity.extract_feature_set")
    def test_active_v2_route_indexes_new_cad_without_shadow_flag(
        self, extract_v1, index_v1, index_v2
    ) -> None:
        feature_set = self.create_feature("post-cutover-upload", 10)
        extract_v1.return_value = feature_set
        index_v1.return_value = feature_set

        result = extract_and_index_cad_model(feature_set.cad_model)

        self.assertEqual(result, feature_set)
        index_v2.assert_called_once_with(feature_set.cad_model)

    def test_deterministic_reranking_prefers_closer_geometry_and_explains_lanes(self) -> None:
        query = self.create_feature("query", 10)
        near = self.create_feature("near", 11)
        far = self.create_feature("far", 30, material_code="PP")
        profile = get_demo_profile()

        near_result = compare_feature_sets(query, near, profile)
        far_result = compare_feature_sets(query, far, profile)

        self.assertGreater(near_result["overall_score"], far_result["overall_score"])
        self.assertTrue(near_result["feature_availability"]["metadata"])
        self.assertIn("effective_weights", near_result)
        self.assertTrue(near_result["similarities"])
        self.assertTrue(far_result["differences"])

    @patch("platform_core.views.run_similarity_job.apply_async")
    def test_search_endpoint_creates_async_job_and_replays_idempotently(self, apply_async) -> None:
        query = self.create_feature("query", 10)
        payload = {
            "query": {"cad_artifact_version_id": str(query.cad_model.artifact_version_id)},
            "filters": {"dataset_ids": ["similarity-test-v1"]},
            "top_k": 5,
            "idempotency_key": "similarity-request-1",
        }

        first = self.client.post(
            "/api/v1/similarity-searches", payload, content_type="application/json"
        )
        second = self.client.post(
            "/api/v1/similarity-searches", payload, content_type="application/json"
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertFalse(first.json()["idempotent_replay"])
        self.assertTrue(second.json()["idempotent_replay"])
        self.assertEqual(first.json()["job_id"], second.json()["job_id"])
        apply_async.assert_called_once_with(args=[first.json()["job_id"]], queue="cad")

    @patch("platform_core.similarity.query_similar_points")
    def test_similarity_job_persists_ranked_result_and_excludes_query(self, query_points) -> None:
        query = self.create_feature("query", 10)
        near = self.create_feature("near", 11)
        far = self.create_feature("far", 25, material_code="PP")
        records = create_similarity_records(
            query.cad_model.artifact_version,
            top_k=5,
            filters={"dataset_ids": ["similarity-test-v1"]},
        )
        query_points.return_value = [
            VectorCandidate(str(query.id), 1.0),
            VectorCandidate(str(near.id), 0.98),
            VectorCandidate(str(far.id), 0.75),
        ]

        task_result = run_similarity_job.run(str(records.job.id))

        records.job.refresh_from_db()
        search = SimilaritySearch.objects.get(pk=records.search.id)
        self.assertEqual(task_result["state"], Job.State.SUCCEEDED)
        self.assertEqual(records.job.state, Job.State.SUCCEEDED)
        self.assertEqual(search.result["result_count"], 2)
        self.assertEqual(search.result["results"][0]["artifact_name"], "near")
        self.assertNotIn(
            str(query.cad_model.artifact_version_id),
            [match["artifact_version_id"] for match in search.result["results"]],
        )
        self.assertEqual(search.result["index_version"], "cad-demo-v1")

        response = self.client.get(f"/api/v1/jobs/{records.job.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["search_id"], str(search.id))

    @override_settings(SIMILARITY_INDEX_READ_VERSION="v2")
    @patch("platform_core.similarity.query_named_vectors")
    def test_v2_route_pins_and_executes_cpu_manufacturing_profile(self, query_points) -> None:
        query_v1 = self.create_feature("query-v2", 10)
        near_v1 = self.create_feature("near-v2", 11)
        error_v1 = self.create_feature(
            "error-control-v2",
            10,
            dataset_id="curated-cad-demo-errors-v1",
        )
        query = extract_feature_set_v2(query_v1.cad_model)
        near = extract_feature_set_v2(near_v1.cad_model)
        error = extract_feature_set_v2(error_v1.cad_model)
        FeatureSet.objects.filter(id__in=[query.id, near.id, error.id]).update(
            index_status=FeatureSet.IndexStatus.INDEXED
        )
        query.refresh_from_db()
        near.refresh_from_db()
        error.refresh_from_db()
        records = create_similarity_records(query.cad_model.artifact_version, top_k=5)
        query_points.return_value = [
            VectorCandidate(str(query.id), 1.0),
            VectorCandidate(str(error.id), 0.99),
            VectorCandidate(str(near.id), 0.98),
        ]

        # The worker must use the submitted policy, not a subsequently changed deployment env.
        with override_settings(SIMILARITY_GEOMETRY_POLICY="cosine-v2"):
            result = run_similarity_job.run(str(records.job.id))

        records.search.refresh_from_db()
        self.assertEqual(result["state"], Job.State.SUCCEEDED)
        self.assertEqual(records.search.query_feature_set.schema_version, "2.0")
        self.assertEqual(records.search.profile.schema_version, "2.0")
        self.assertEqual(records.job.input_snapshot["read_version"], "v2")
        self.assertEqual(records.search.result["index_version"], "cad-cpu-v2")
        match = records.search.result["results"][0]
        self.assertEqual(records.search.result["result_count"], 1)
        self.assertEqual(match["artifact_name"], "near-v2")
        self.assertEqual(
            records.job.input_snapshot["geometry_ranking_policy"], "block-distance@1.0"
        )
        self.assertEqual(match["geometry_ranking"]["policy"], "block-distance@1.0")
        self.assertIn("manufacturing", match["sub_scores"])
        self.assertTrue(match["similarities"])
        self.assertTrue(match["differences"])
        self.assertLess(match["evidence_coverage"], 1.0)
        self.assertLess(match["overall_score"], match["available_lane_score"])
        query_points.assert_called_once()

    @patch("platform_core.views.run_similarity_job.apply_async", side_effect=ConnectionError)
    def test_queue_failure_is_typed_without_corrupting_cad_geometry(self, apply_async) -> None:
        query = self.create_feature("query", 10)
        response = self.client.post(
            "/api/v1/similarity-searches",
            {
                "query": {"cad_artifact_version_id": str(query.cad_model.artifact_version_id)},
                "top_k": 5,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "JOB_QUEUE_UNAVAILABLE")
        similarity_job = Job.objects.filter(capability_id="mold.similarity_search").get()
        self.assertEqual(similarity_job.state, Job.State.FAILED)
        query.cad_model.refresh_from_db()
        self.assertEqual(query.cad_model.geometry_status, "succeeded")
        apply_async.assert_called_once()

    def test_rejects_unknown_profile_and_malformed_query_uuid(self) -> None:
        malformed = self.client.post(
            "/api/v1/similarity-searches",
            {"query": {"cad_artifact_version_id": "not-a-uuid"}},
            content_type="application/json",
        )
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json()["error"]["code"], "VALIDATION_QUERY_ARTIFACT")

        query = self.create_feature("query", 10)
        unknown_profile = self.client.post(
            "/api/v1/similarity-searches",
            {
                "query": {"cad_artifact_version_id": str(query.cad_model.artifact_version_id)},
                "profile": "unknown@9.9",
            },
            content_type="application/json",
        )
        self.assertEqual(unknown_profile.status_code, 400)
        self.assertEqual(unknown_profile.json()["error"]["code"], "VALIDATION_SIMILARITY_PROFILE")
