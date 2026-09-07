from tempfile import TemporaryDirectory

import numpy as np
import trimesh
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings

from platform_core.cad_registration import (
    RegistrationValidationError,
    compute_registration,
)
from platform_core.models import (
    Artifact,
    ArtifactVersion,
    CADModel,
    FeatureSet,
    Job,
    SimilarityProfile,
    SimilaritySearch,
)


class RegistrationAlgorithmTests(TestCase):
    def test_high_score_runs_icp_and_returns_signed_deviation_cloud(self) -> None:
        query = trimesh.creation.box(extents=(8.0, 4.0, 2.0))
        candidate = query.copy()
        candidate.apply_transform(trimesh.transformations.rotation_matrix(0.4, [0.2, 1.0, 0.5]))
        candidate.apply_translation([9.0, -4.0, 2.5])

        result = compute_registration(
            query, candidate, overall_score=0.95, sample_count=384, seed=77
        )

        self.assertEqual(result.alignment_status, "full")
        self.assertTrue(result.result["alignment"]["icp_attempted"])
        self.assertTrue(result.result["alignment"]["icp_converged"])
        self.assertEqual(result.result["deviation"]["mode"], "signed")
        self.assertLess(result.result["deviation"]["rmse"], 0.05)
        self.assertEqual(len(result.transform), 4)

    def test_low_score_skips_icp_and_open_mesh_uses_unsigned_distance(self) -> None:
        query = trimesh.creation.box(extents=(4.0, 3.0, 2.0))
        query.update_faces(np.arange(len(query.faces) - 1))
        candidate = query.copy()

        result = compute_registration(
            query, candidate, overall_score=0.5, sample_count=256, seed=44
        )

        self.assertEqual(result.alignment_status, "skipped")
        self.assertFalse(result.result["alignment"]["icp_attempted"])
        self.assertEqual(result.result["deviation"]["mode"], "unsigned")

    def test_roi_rejects_empty_or_reversed_bounds(self) -> None:
        mesh = trimesh.creation.box()
        with self.assertRaises(RegistrationValidationError) as reversed_bounds:
            compute_registration(
                mesh,
                mesh,
                overall_score=0.9,
                roi={"min": [1, 0, 0], "max": [0, 1, 1]},
                sample_count=256,
            )
        self.assertEqual(reversed_bounds.exception.code, "VALIDATION_ROI")


class RegistrationEndpointTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.override.enable()

    def tearDown(self) -> None:
        self.override.disable()
        self.media_directory.cleanup()

    def _feature(self, name: str, suffix: str) -> FeatureSet:
        artifact = Artifact.objects.create(name=name, kind=Artifact.Kind.CAD_SOURCE)
        source = ArtifactVersion.objects.create(
            artifact=artifact,
            version_number=1,
            original_filename=f"{name}.stl",
            media_type="model/stl",
            format="stl",
            size_bytes=1,
            sha256=suffix * 64,
            storage_key=f"tests/{name}-source.stl",
        )
        preview_artifact = Artifact.objects.create(
            name=f"{name} preview", kind=Artifact.Kind.CAD_PREVIEW
        )
        preview_content = trimesh.creation.box(extents=(8, 4, 2)).export(file_type="stl")
        preview = ArtifactVersion.objects.create(
            artifact=preview_artifact,
            version_number=1,
            original_filename=f"{name}-preview.stl",
            media_type="model/stl",
            format="stl",
            size_bytes=len(preview_content),
            sha256=(suffix.upper()) * 64,
            storage_key=f"tests/{name}-preview.stl",
        )
        default_storage.save(preview.storage_key, ContentFile(preview_content))
        cad = CADModel.objects.create(
            artifact_version=source,
            preview_artifact_version=preview,
            geometry_status=CADModel.GeometryStatus.SUCCEEDED,
        )
        return FeatureSet.objects.create(
            cad_model=cad,
            schema_version="1.0",
            extractor_version="endpoint-test",
            vector=[1.0] + [0.0] * 11,
            vector_dimension=12,
            vector_checksum=suffix * 64,
            index_collection="test",
            index_version="test-v1",
            index_status=FeatureSet.IndexStatus.INDEXED,
        )

    def test_comparison_is_scoped_to_search_result_and_idempotent(self) -> None:
        query = self._feature("query", "a")
        candidate = self._feature("candidate", "b")
        profile = SimilarityProfile.objects.create(
            profile_key="registration-test",
            weights={"geometry": 1.0},
            candidate_collection="test",
            index_version="test-v1",
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
                        "overall_score": 0.95,
                    }
                ]
            },
        )
        url = (
            f"/api/v1/similarity-searches/{search.id}/candidates/"
            f"{candidate.cad_model.artifact_version_id}/comparison"
        )

        first = self.client.post(url, {}, content_type="application/json")
        second = self.client.post(url, {}, content_type="application/json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.json()["created"])
        self.assertFalse(second.json()["created"])
        self.assertEqual(first.json()["comparison_id"], second.json()["comparison_id"])
        self.assertIn(first.json()["alignment_status"], {"full", "partial"})

    def test_candidate_outside_result_is_denied_before_geometry_access(self) -> None:
        query = self._feature("query-deny", "c")
        candidate = self._feature("candidate-deny", "d")
        profile = SimilarityProfile.objects.create(
            profile_key="registration-deny-test",
            weights={"geometry": 1.0},
            candidate_collection="test",
            index_version="test-v1",
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
            job=job, query_feature_set=query, profile=profile, result={"results": []}
        )

        response = self.client.post(
            f"/api/v1/similarity-searches/{search.id}/candidates/"
            f"{candidate.cad_model.artifact_version_id}/comparison",
            {},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "SIMILARITY_CANDIDATE_NOT_AUTHORIZED")
