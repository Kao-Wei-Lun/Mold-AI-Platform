from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from platform_core.knowledge import (
    AUTOMATED_SMOKE_DATASET,
    PUBLIC_KNOWLEDGE_DATASET,
    create_knowledge_upload_records,
)
from platform_core.knowledge_fixtures import seed_demo_knowledge


class DemoKnowledgeSeedTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    @patch("platform_core.knowledge.upsert_named_vector")
    def test_seed_is_idempotent_and_relabels_legacy_smoke_documents(self, upsert) -> None:
        smoke = create_knowledge_upload_records(
            SimpleUploadedFile(
                "legacy-smoke.md",
                b"# Legacy smoke\n\nThis content is test-only.",
                content_type="text/markdown",
            ),
            title="Stage 5 smoke knowledge guide",
            document_type="design_guideline",
            authority_level="reviewed_demo",
            owner="smoke-test",
            language="en",
            effective_from=None,
            effective_to=None,
            idempotency_key="legacy-smoke-before-dataset-isolation",
            dataset_id=PUBLIC_KNOWLEDGE_DATASET,
        )

        first = seed_demo_knowledge()
        second = seed_demo_knowledge()

        smoke.artifact.refresh_from_db()
        self.assertEqual(smoke.artifact.dataset_id, AUTOMATED_SMOKE_DATASET)
        self.assertEqual(first.created, 1)
        self.assertEqual(first.indexed, 1)
        self.assertEqual(first.relabeled_smoke_documents, 1)
        self.assertEqual(second.created, 0)
        self.assertEqual(second.existing, 1)
        self.assertEqual(second.document_ids, first.document_ids)
        upsert.assert_called()
