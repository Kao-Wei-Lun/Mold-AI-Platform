from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from platform_core.cad_fixtures import (
    AUTOMATED_CAD_SMOKE_DATASET,
    CURATED_CAD_DATASET,
    curated_cad_status,
    load_cad_manifest,
    seed_curated_cad_demo,
)
from platform_core.models import Artifact, FeatureSet


class CuratedCADSeedTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name,
            SIMILARITY_AUTO_INDEX=True,
        )
        self.settings_override.enable()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    def test_manifest_has_versioned_checksummed_normal_and_error_corpora(self) -> None:
        manifest, manifest_sha256 = load_cad_manifest()

        self.assertEqual(manifest["dataset_id"], CURATED_CAD_DATASET)
        self.assertEqual(len(manifest["fixtures"]), 16)
        self.assertEqual(len(manifest["error_controls"]), 2)
        self.assertEqual(len(manifest_sha256), 64)
        self.assertNotIn("PENDING", str(manifest))

    @patch("platform_core.similarity.upsert_feature")
    def test_seed_replay_partial_reconciliation_and_golden_invariants(self, upsert) -> None:
        first = seed_curated_cad_demo()
        second = seed_curated_cad_demo()

        self.assertEqual(first.created, 16)
        self.assertEqual(first.verified, 16)
        self.assertEqual(first.error_controls_verified, 2)
        self.assertEqual(first.golden_similarity_verified, 2)
        self.assertEqual(first.golden_review_verified, 4)
        self.assertEqual(second.created, 0)
        self.assertEqual(second.existing, 16)
        self.assertEqual(second.artifact_version_ids, first.artifact_version_ids)

        FeatureSet.objects.filter(
            cad_model__artifact_version_id=first.artifact_version_ids[0]
        ).delete()
        repaired = seed_curated_cad_demo()
        self.assertEqual(repaired.reconciled, 1)

        verified = seed_curated_cad_demo(verify_only=True)
        self.assertEqual(verified.reconciled, 0)
        status = curated_cad_status()
        self.assertTrue(status["reconciled"])
        self.assertEqual(status["ready"], 16)
        self.assertEqual(status["indexed"], 16)
        self.assertGreaterEqual(upsert.call_count, 17)

    @patch("platform_core.similarity.upsert_feature")
    def test_management_command_supports_seed_and_read_only_verification(self, upsert) -> None:
        call_command("seed_cad_demo")
        call_command("seed_cad_demo", "--verify-only")

    def test_default_cad_listing_excludes_automated_smoke_dataset(self) -> None:
        Artifact.objects.create(
            name="Smoke CAD",
            kind=Artifact.Kind.CAD_SOURCE,
            classification="public_demo",
            dataset_id=AUTOMATED_CAD_SMOKE_DATASET,
        )
        curated = Artifact.objects.create(
            name="Curated CAD",
            kind=Artifact.Kind.CAD_SOURCE,
            classification="public_demo",
            dataset_id=CURATED_CAD_DATASET,
        )

        response = self.client.get("/api/v1/cad-artifacts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["artifact_id"] for item in response.json()["items"]], [str(curated.id)]
        )

        smoke = self.client.get(
            "/api/v1/cad-artifacts", {"dataset_id": AUTOMATED_CAD_SMOKE_DATASET}
        )
        self.assertEqual(len(smoke.json()["items"]), 1)
