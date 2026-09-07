import trimesh
from django.test import TestCase, override_settings

from platform_core.cad_manufacturing import (
    PROFILE_DEFINITIONS,
    compare_feature_sets_v2,
    extract_manufacturing_features,
    manufacturing_similarity,
    resolve_similarity_profile,
)
from platform_core.models import Artifact, ArtifactVersion, CADModel, FeatureSet


class ManufacturingFeatureTests(TestCase):
    def test_stl_defaults_to_not_available(self) -> None:
        result = extract_manufacturing_features(trimesh.creation.box(), source_format="stl")

        self.assertEqual(result["availability"], "NOT_AVAILABLE")
        self.assertEqual(result["reason_code"], "STL_HAS_NO_BREP_TOPOLOGY")
        self.assertIsNone(result["wall_thickness"])

    def test_optional_stl_path_only_exposes_approximate_thickness(self) -> None:
        result = extract_manufacturing_features(
            trimesh.creation.box(extents=(8, 5, 2)),
            source_format="stl",
            allow_stl_approximation=True,
            sample_count=64,
        )

        self.assertEqual(result["availability"], "APPROXIMATE")
        self.assertIsNotNone(result["wall_thickness"])
        self.assertIsNone(result["undercut"])
        self.assertIsNone(result["parting"])

    def test_step_preview_returns_manufacturing_evidence_and_planar_parting(self) -> None:
        result = extract_manufacturing_features(
            trimesh.creation.box(extents=(8, 5, 2)),
            source_format="step",
            sample_count=64,
        )

        self.assertEqual(result["availability"], "APPROXIMATE")
        self.assertEqual(result["reason_code"], "STEP_DERIVED_TESSELLATION")
        self.assertGreater(result["wall_thickness"]["nominal"], 0)
        self.assertEqual(result["undercut"]["estimated_slide_count"], 0)
        self.assertEqual(result["parting"]["classification"], "FLAT_PLANE")

    def test_manufacturing_similarity_returns_engineering_evidence(self) -> None:
        artifact = Artifact.objects.create(name="part", kind=Artifact.Kind.CAD_SOURCE)
        version = ArtifactVersion.objects.create(
            artifact=artifact,
            version_number=1,
            original_filename="part.step",
            media_type="model/step",
            format="step",
            size_bytes=1,
            sha256="3" * 64,
            storage_key="tests/part.step",
        )
        cad = CADModel.objects.create(
            artifact_version=version,
            geometry_status=CADModel.GeometryStatus.SUCCEEDED,
        )
        manufacturing = {
            "availability": "APPROXIMATE",
            "wall_thickness": {"nominal": 2.0, "max_ratio": 1.1, "coefficient_of_variation": 0.1},
            "undercut": {"projected_area_ratio": 0.2, "estimated_slide_count": 2},
            "parting": {"classification": "FLAT_PLANE"},
        }
        first = FeatureSet.objects.create(
            cad_model=cad,
            schema_version="2.0",
            extractor_version="test-a",
            features={"manufacturing": manufacturing},
            vector=[1.0],
            vector_dimension=1,
            vector_checksum="a" * 64,
            index_collection="test",
            index_version="test",
        )
        second = FeatureSet.objects.create(
            cad_model=cad,
            schema_version="2.0",
            extractor_version="test-b",
            features={"manufacturing": manufacturing},
            vector=[1.0],
            vector_dimension=1,
            vector_checksum="b" * 64,
            index_collection="test",
            index_version="test",
        )

        score, evidence = manufacturing_similarity(first, second)

        self.assertEqual(score, 1.0)
        self.assertIn("Similar undercut count (2 slides required).", evidence)
        self.assertIn("Parting line is planar on both parts.", evidence)


class SimilarityProfileResolutionTests(TestCase):
    @override_settings(
        QDRANT_CAD_COLLECTION_V2="cad-v2-test", SIMILARITY_INDEX_VERSION_V2="cpu-v2-test"
    )
    def test_family_profile_resolution_is_deterministic_and_auditable(self) -> None:
        artifact = Artifact.objects.create(
            name="connector", kind=Artifact.Kind.CAD_SOURCE, product_type="precision_connector"
        )
        version = ArtifactVersion.objects.create(
            artifact=artifact,
            version_number=1,
            original_filename="connector.step",
            media_type="model/step",
            format="step",
            size_bytes=1,
            sha256="4" * 64,
            storage_key="tests/connector.step",
        )
        cad = CADModel.objects.create(artifact_version=version)

        resolution = resolve_similarity_profile(cad)

        self.assertEqual(resolution.profile.profile_key, "precision-connector@2.0")
        self.assertEqual(resolution.resolution["reason_code"], "PRODUCT_FAMILY_CONNECTOR")
        self.assertEqual(resolution.profile.weights, PROFILE_DEFINITIONS["precision-connector@2.0"])
        self.assertAlmostEqual(sum(resolution.profile.weights.values()), 1.0)

    @override_settings(
        QDRANT_CAD_COLLECTION_V2="cad-v2-test", SIMILARITY_INDEX_VERSION_V2="cpu-v2-test"
    )
    def test_missing_manufacturing_lane_is_removed_and_weights_are_renormalized(self) -> None:
        artifact = Artifact.objects.create(
            name="housing", kind=Artifact.Kind.CAD_SOURCE, product_type="housing"
        )
        version = ArtifactVersion.objects.create(
            artifact=artifact,
            version_number=1,
            original_filename="housing.stl",
            media_type="model/stl",
            format="stl",
            size_bytes=1,
            sha256="5" * 64,
            storage_key="tests/housing.stl",
        )
        cad = CADModel.objects.create(artifact_version=version)
        features = {
            "dimension": {"sorted": [8, 5, 2], "unit_system": "mm"},
            "topology": {
                "face_count": 12,
                "edge_count": 18,
                "surface_type_histogram": {"plane": 12},
            },
            "metadata": {"product_type": "housing", "material_code": "ABS"},
            "manufacturing": {"availability": "NOT_AVAILABLE"},
        }
        vector = [1.0] + [0.0] * 31
        first = FeatureSet.objects.create(
            cad_model=cad,
            schema_version="2.0",
            extractor_version="compare-a",
            features=features,
            vector=vector,
            vector_dimension=32,
            vector_checksum="c" * 64,
            index_collection="test",
            index_version="test",
        )
        second = FeatureSet.objects.create(
            cad_model=cad,
            schema_version="2.0",
            extractor_version="compare-b",
            features=features,
            vector=vector,
            vector_dimension=32,
            vector_checksum="d" * 64,
            index_collection="test",
            index_version="test",
        )
        profile = resolve_similarity_profile(cad).profile

        comparison = compare_feature_sets_v2(first, second, profile)

        self.assertIsNone(comparison["sub_scores"]["manufacturing"])
        self.assertFalse(comparison["feature_availability"]["manufacturing"])
        self.assertNotIn("manufacturing", comparison["effective_weights"])
        self.assertAlmostEqual(sum(comparison["effective_weights"].values()), 1.0, places=5)
