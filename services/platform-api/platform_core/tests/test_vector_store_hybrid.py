from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from platform_core.vector_store import (
    collection_info,
    create_collection_snapshot,
    exact_point_count,
    query_hybrid_points,
    replace_collection_alias,
    upsert_hybrid_point,
)


@override_settings(QDRANT_URL="http://qdrant.test:6333")
class HybridVectorStoreTests(SimpleTestCase):
    @patch("platform_core.vector_store._request")
    def test_collection_operations_use_qdrant_management_contract(self, request):
        request.side_effect = [
            {"result": {"status": "green"}},
            {"result": {"count": 7}},
            {"result": {"name": "snapshot-1"}},
        ]

        self.assertEqual(collection_info("cad v2")["status"], "green")
        self.assertEqual(exact_point_count("cad v2"), 7)
        self.assertEqual(create_collection_snapshot("cad v2")["name"], "snapshot-1")
        self.assertIn("cad%20v2", request.call_args_list[0].args[1])

    @patch("platform_core.vector_store._request")
    def test_alias_replacement_is_one_atomic_action_list(self, request):
        request.side_effect = [
            {"result": {"aliases": [{"alias_name": "cad-active"}]}},
            {"result": {}},
        ]

        replace_collection_alias(alias_name="cad-active", collection_name="cad-v2")

        payload = request.call_args_list[1].args[2]
        self.assertEqual(request.call_args_list[1].args[1], "/collections/aliases")
        self.assertEqual(payload["actions"][0]["delete_alias"]["alias_name"], "cad-active")
        self.assertEqual(payload["actions"][1]["create_alias"]["collection_name"], "cad-v2")

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
