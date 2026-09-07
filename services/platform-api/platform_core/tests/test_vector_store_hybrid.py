from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from platform_core.vector_store import query_hybrid_points, upsert_hybrid_point


@override_settings(QDRANT_URL="http://qdrant.test:6333")
class HybridVectorStoreTests(SimpleTestCase):
    @patch("platform_core.vector_store.ensure_hybrid_collection")
    @patch("platform_core.vector_store._request")
    def test_upsert_uses_named_dense_and_sparse_vectors(self, request, ensure):
        upsert_hybrid_point(
            collection_name="knowledge-v2",
            dimension=512,
            point_id="chunk-1",
            dense=[0.1, 0.2],
            sparse_indices=[4, 9],
            sparse_values=[1.0, 2.0],
            payload={"active": True},
        )

        ensure.assert_called_once_with("knowledge-v2", 512)
        point = request.call_args.args[2]["points"][0]
        self.assertEqual(point["vector"]["dense"], [0.1, 0.2])
        self.assertEqual(point["vector"]["sparse"]["indices"], [4, 9])

    @patch("platform_core.vector_store._request")
    def test_query_applies_acl_filter_to_both_prefetches_before_rrf(self, request):
        request.return_value = {"result": {"points": [{"id": "chunk-1", "score": 0.8}]}}

        result = query_hybrid_points(
            collection_name="knowledge-v2",
            dense=[0.1, 0.2],
            sparse_indices=[4],
            sparse_values=[1.0],
            limit=30,
            filters={"classification": "public_demo", "acl_scopes": ["public-demo"]},
        )

        payload = request.call_args.args[2]
        self.assertEqual(payload["query"], {"fusion": "rrf"})
        self.assertEqual(payload["prefetch"][0]["filter"], payload["prefetch"][1]["filter"])
        self.assertEqual(result[0].feature_set_id, "chunk-1")
