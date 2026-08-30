from django.test import SimpleTestCase

from platform_core.deep_links import (
    DeepLinkBuilder,
    DeepLinkConfigurationError,
    DeepLinkValidationError,
    deep_link_readiness,
)

SEARCH_ID = "11111111-1111-4111-8111-111111111111"
CANDIDATE_ID = "22222222-2222-4222-8222-222222222222"
PROFILE_ID = "33333333-3333-4333-8333-333333333333"
BATCH_ID = "44444444-4444-4444-8444-444444444444"


class DeepLinkBuilderTests(SimpleTestCase):
    def test_builds_versioned_allowlisted_link_with_canonical_ids(self) -> None:
        link = DeepLinkBuilder("https://mold-ai.example.test/").build(
            "similarity",
            search_id=SEARCH_ID,
            candidate_id=CANDIDATE_ID,
        )

        self.assertEqual(
            link,
            "https://mold-ai.example.test/open?deep_link_version=1.0&target=similarity"
            f"&candidate_id={CANDIDATE_ID}&search_id={SEARCH_ID}",
        )

    def test_rejects_non_deployable_entry_origins_and_credentials(self) -> None:
        for value in (
            "http://mold-ai.example.test",
            "https://localhost",
            "https://dynamic.invalid",
            "https://user:password@mold-ai.example.test",
            "https://mold-ai.example.test/path",
            "https://mold-ai.example.test?token=secret",
        ):
            with self.subTest(value=value), self.assertRaises(DeepLinkConfigurationError):
                DeepLinkBuilder(value)

    def test_builds_governed_profile_and_import_batch_links(self) -> None:
        builder = DeepLinkBuilder("https://mold-ai.example.test")

        self.assertIn(
            f"target=rule_profile&profile_id={PROFILE_ID}",
            builder.build("rule_profile", profile_id=PROFILE_ID),
        )
        self.assertIn(
            f"target=ingestion_batch&batch_id={BATCH_ID}",
            builder.build("ingestion_batch", batch_id=BATCH_ID),
        )

    def test_rejects_unknown_targets_refs_sensitive_fields_and_non_uuid_ids(self) -> None:
        builder = DeepLinkBuilder("https://mold-ai.example.test")
        invalid_calls = (
            lambda: builder.build("unknown"),
            lambda: builder.build("similarity"),
            lambda: builder.build("home", return_url="https://attacker.test"),
            lambda: builder.build("job", job_id="job-1"),
            lambda: builder.build("job", job_id=SEARCH_ID, extra="value"),
        )
        for call in invalid_calls:
            with self.assertRaises(DeepLinkValidationError):
                call()

    def test_readiness_is_safe_and_does_not_echo_invalid_input(self) -> None:
        invalid = deep_link_readiness("https://user:secret@dynamic.invalid?token=secret")
        ready = deep_link_readiness("https://mold-ai.example.test")

        self.assertFalse(invalid["ready"])
        self.assertIsNone(invalid["entry_origin"])
        self.assertNotIn("secret", str(invalid))
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["entry_origin"], "https://mold-ai.example.test")

    def test_local_http_is_an_explicit_development_only_exception(self) -> None:
        with self.assertRaises(DeepLinkConfigurationError):
            DeepLinkBuilder("http://localhost:5173")

        link = DeepLinkBuilder("http://localhost:5173", allow_local=True).build("home")
        self.assertEqual(
            link,
            "http://localhost:5173/open?deep_link_version=1.0&target=home",
        )
