from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import trimesh
from django.test import TestCase, override_settings

from platform_core.cad_similarity_v2 import (
    EXTRACTOR_VERSION,
    FEATURE_SCHEMA_VERSION,
    VECTOR_DIMENSION,
    CADSimilarityV2Error,
    extract_feature_set_v2,
    extract_shape_descriptor,
    index_feature_set_v2,
)
from platform_core.models import Artifact, ArtifactVersion, CADModel, FeatureSet


class ShapeDescriptorTests(TestCase):
    def test_descriptor_is_deterministic_scale_translation_and_rotation_invariant(self) -> None:
        source = trimesh.creation.box(extents=(8.0, 3.0, 1.5))
        first = extract_shape_descriptor(source, sample_count=1024, seed=91)

        transformed = source.copy()
        transform = trimesh.transformations.rotation_matrix(np.pi / 3, [1.0, 2.0, 3.0])
        transformed.apply_transform(transform)
        transformed.apply_scale(7.25)
        transformed.apply_translation([100.0, -24.0, 8.0])
        second = extract_shape_descriptor(transformed, sample_count=1024, seed=91)

        self.assertEqual(len(first.vector), VECTOR_DIMENSION)
        self.assertTrue(np.allclose(first.vector, second.vector, atol=1e-7))
        self.assertEqual(
            first.features["extraction_manifest"]["random_seed"],
            second.features["extraction_manifest"]["random_seed"],
        )

    def test_open_mesh_records_solidity_as_not_available(self) -> None:
        mesh = trimesh.creation.box()
        mesh.update_faces(np.arange(len(mesh.faces) - 1))
        result = extract_shape_descriptor(mesh, sample_count=512)

        self.assertEqual(result.features["availability"]["solidity"], "NOT_AVAILABLE")
        self.assertIsNone(result.features["shape_invariants"]["solidity"])


class FeatureSetV2Tests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    def _cad_model(self) -> CADModel:
        source_artifact = Artifact.objects.create(name="source", kind=Artifact.Kind.CAD_SOURCE)
        source_version = ArtifactVersion.objects.create(
            artifact=source_artifact,
            version_number=1,
            original_filename="source.stl",
            media_type="model/stl",
            format="stl",
            size_bytes=1,
            sha256="1" * 64,
            storage_key="test/source.stl",
        )
        preview_artifact = Artifact.objects.create(name="preview", kind=Artifact.Kind.CAD_PREVIEW)
        mesh = trimesh.creation.icosphere(subdivisions=2)
        preview_bytes = mesh.export(file_type="stl")
        preview_version = ArtifactVersion.objects.create(
            artifact=preview_artifact,
            version_number=1,
            original_filename="preview.stl",
            media_type="model/stl",
            format="stl",
            size_bytes=len(preview_bytes),
            sha256="2" * 64,
            storage_key="test/preview.stl",
        )
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        default_storage.save(preview_version.storage_key, ContentFile(preview_bytes))
        return CADModel.objects.create(
            artifact_version=source_version,
            preview_artifact_version=preview_version,
            geometry_status=CADModel.GeometryStatus.SUCCEEDED,
            unit_system="mm",
        )

    def test_feature_contract_persists_manifest_and_reuses_checksum(self) -> None:
        cad_model = self._cad_model()
        first = extract_feature_set_v2(cad_model)
        second = extract_feature_set_v2(cad_model)

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.schema_version, FEATURE_SCHEMA_VERSION)
        self.assertEqual(first.extractor_version, EXTRACTOR_VERSION)
        self.assertEqual(first.vector_dimension, VECTOR_DIMENSION)
        self.assertEqual(len(first.vector), VECTOR_DIMENSION)
        self.assertEqual(len(first.vector_checksum), 64)
        self.assertEqual(first.features["source"]["unit_system"], "mm")

    @patch("platform_core.cad_similarity_v2.upsert_named_vector")
    def test_index_payload_carries_acl_and_version_contract(self, upsert) -> None:
        feature_set = extract_feature_set_v2(self._cad_model())
        indexed = index_feature_set_v2(feature_set)

        self.assertEqual(indexed.index_status, FeatureSet.IndexStatus.INDEXED)
        payload = upsert.call_args.kwargs["payload"]
        self.assertEqual(payload["classification"], "public_demo")
        self.assertEqual(payload["feature_schema_version"], "2.0")
        self.assertEqual(upsert.call_args.kwargs["dimension"], 32)

    def test_missing_preview_is_a_typed_error(self) -> None:
        cad_model = self._cad_model()
        cad_model.preview_artifact_version = None
        cad_model.save(update_fields=["preview_artifact_version"])

        with self.assertRaises(CADSimilarityV2Error) as caught:
            extract_feature_set_v2(cad_model)

        self.assertEqual(caught.exception.code, "CAD_PREVIEW_NOT_AVAILABLE")
