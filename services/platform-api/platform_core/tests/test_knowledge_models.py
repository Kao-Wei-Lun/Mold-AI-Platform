from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from platform_core.knowledge_models import (
    DENSE_DIMENSION,
    _flashrank_is_packaged,
    dense_encode,
    expand_domain_query,
    load_abstention_calibration,
    sparse_encode,
)


class KnowledgeModelContractTests(SimpleTestCase):
    @override_settings(
        EMBEDDING_MODEL_PATH="/missing/embedding-model",
        RAG_CPU_MODELS_REQUIRED=False,
    )
    def test_offline_fallback_is_deterministic_and_provenanced(self):
        first = dense_encode("短射 short shot")
        second = dense_encode("短射 short shot")

        self.assertEqual(first.vector, second.vector)
        self.assertEqual(first.checksum, second.checksum)
        self.assertEqual(first.dimension, DENSE_DIMENSION)
        self.assertEqual(len(first.vector), DENSE_DIMENSION)
        self.assertEqual(first.mode, "degraded")

    def test_domain_synonyms_and_sparse_indices_are_deterministic(self):
        expanded, additions = expand_domain_query("如何處理短射？")
        first = sparse_encode(expanded)
        second = sparse_encode(expanded)

        self.assertIn("short shot", additions)
        self.assertIn("充填不足", expanded)
        self.assertEqual(first, second)
        self.assertEqual(first.indices, sorted(set(first.indices)))
        self.assertEqual(len(first.indices), len(first.values))

    def test_calibration_is_versioned_and_approved(self):
        calibration = load_abstention_calibration()

        self.assertEqual(calibration["schema_version"], "1.0")
        self.assertTrue(calibration["approved_by"])
        self.assertGreater(float(calibration["threshold"]), 0)

    def test_flashrank_is_not_initialized_from_an_empty_cache(self):
        with TemporaryDirectory() as cache_dir:
            with override_settings(RERANKER_MODEL_PATH=cache_dir):
                self.assertFalse(_flashrank_is_packaged())
