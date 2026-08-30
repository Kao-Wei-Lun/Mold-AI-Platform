from datetime import date, timedelta
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from platform_core.design_review import create_design_review_records, get_demo_rule_profile
from platform_core.ingestion import create_upload_records
from platform_core.models import (
    Artifact,
    DataScope,
    Mold,
    MoldRevision,
    ProductPart,
    Project,
    RuleProfile,
    RuleProfileApplicability,
)
from platform_core.rule_resolution import RuleResolutionError, resolve_rule_profile
from platform_core.tasks import process_cad_job
from platform_core.tests.fixtures import ASCII_TETRAHEDRON_STL


@override_settings(SIMILARITY_AUTO_INDEX=False)
class RuleResolutionTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        scope = DataScope.objects.get(code="public-demo")
        project = Project.objects.create(scope=scope, code="RULE-PROJECT", name="Rule project")
        part = ProductPart.objects.create(
            project=project,
            part_number="RULE-PART",
            name="Rule part",
            product_type="housing",
            material_code="ABS-GENERAL",
        )
        mold = Mold.objects.create(
            project=project,
            product_part=part,
            mold_code="RULE-MOLD",
            name="Rule mold",
            mold_type="three_plate",
        )
        revision = MoldRevision.objects.create(
            mold=mold, revision_code="A", status=MoldRevision.Status.RELEASED
        )
        records = create_upload_records(
            SimpleUploadedFile(
                "rule-part.stl", ASCII_TETRAHEDRON_STL, content_type="model/stl"
            ),
            artifact_name="Rule resolution fixture",
        )
        process_cad_job.run(str(records.job.id))
        Artifact.objects.filter(pk=records.artifact.pk).update(
            mold_revision=revision,
            product_type="housing",
            material_code="ABS-GENERAL",
        )
        self.version = records.version
        self.scope = scope
        self.default = get_demo_rule_profile()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.media_directory.cleanup()

    def profile(
        self,
        key: str,
        *,
        priority: int,
        dimensions: dict[str, str],
        effective_from: date | None = None,
        effective_to: date | None = None,
    ) -> RuleProfile:
        profile = RuleProfile.objects.create(
            profile_key=key,
            version="1.0",
            owner="rule-owner",
            approved_by="approver",
            ruleset_checksum="resolver-test",
            workflow_status=RuleProfile.WorkflowStatus.PUBLISHED,
            priority=priority,
            scope=self.scope,
            classification="public_demo",
            effective_from=effective_from,
            effective_to=effective_to,
        )
        RuleProfileApplicability.objects.bulk_create(
            [
                RuleProfileApplicability(
                    profile=profile,
                    dimension=dimension,
                    value_code=value,
                )
                for dimension, value in dimensions.items()
            ]
        )
        return profile

    def test_specificity_then_priority_selects_profile_and_records_reason(self) -> None:
        self.profile(
            "three-plate-low",
            priority=10,
            dimensions={"mold_type": "three_plate"},
        )
        selected = self.profile(
            "three-plate-housing",
            priority=5,
            dimensions={"mold_type": "three_plate", "product_type": "housing"},
        )
        self.profile(
            "three-plate-housing-high",
            priority=20,
            dimensions={"mold_type": "three_plate", "product_type": "other"},
        )

        resolution = resolve_rule_profile(self.version)

        self.assertEqual(resolution.profile, selected)
        self.assertEqual(resolution.snapshot["selected"]["specificity"], 2)
        self.assertEqual(
            resolution.snapshot["context"]["molding_process"], "injection"
        )
        self.assertIn("most specific", resolution.snapshot["reason"])

    def test_equal_specificity_and_priority_fails_closed(self) -> None:
        for key in ("ambiguous-a", "ambiguous-b"):
            self.profile(
                key,
                priority=50,
                dimensions={"mold_type": "three_plate"},
            )

        with self.assertRaises(RuleResolutionError) as caught:
            resolve_rule_profile(self.version)

        self.assertEqual(caught.exception.code, "RULE_PROFILE_AMBIGUOUS")
        self.assertGreaterEqual(len(caught.exception.candidates), 3)

    def test_profile_from_another_scope_is_not_visible(self) -> None:
        foreign_scope = DataScope.objects.create(
            code="company-private",
            name="Company private",
            classification="public_demo",
        )
        foreign = RuleProfile.objects.create(
            profile_key="foreign-three-plate",
            version="1.0",
            owner="foreign-owner",
            approved_by="foreign-approver",
            ruleset_checksum="foreign",
            workflow_status=RuleProfile.WorkflowStatus.PUBLISHED,
            priority=999,
            scope=foreign_scope,
            classification="public_demo",
        )
        RuleProfileApplicability.objects.create(
            profile=foreign,
            dimension="mold_type",
            value_code="three_plate",
        )

        resolution = resolve_rule_profile(self.version)

        self.assertEqual(resolution.profile, self.default)
        self.assertNotIn(
            str(foreign.id),
            {candidate["profile_id"] for candidate in resolution.snapshot["candidates"]},
        )

    def test_expired_profiles_are_ignored_and_manual_override_requires_reason(self) -> None:
        expired = self.profile(
            "expired-profile",
            priority=999,
            dimensions={"mold_type": "three_plate"},
            effective_to=date.today() - timedelta(days=1),
        )
        eligible = self.profile(
            "eligible-profile",
            priority=1,
            dimensions={"mold_type": "three_plate"},
        )
        self.assertEqual(resolve_rule_profile(self.version).profile, eligible)
        with self.assertRaises(RuleResolutionError) as caught:
            resolve_rule_profile(
                self.version,
                requested_profile_id=str(expired.id),
                override_reason="Use legacy profile",
            )
        self.assertEqual(caught.exception.code, "RULE_PROFILE_OVERRIDE_NOT_ELIGIBLE")
        with self.assertRaises(RuleResolutionError) as missing_reason:
            resolve_rule_profile(self.version, requested_profile_id=str(eligible.id))
        self.assertEqual(missing_reason.exception.code, "VALIDATION_OVERRIDE_REASON")

    def test_design_review_keeps_immutable_resolution_snapshot(self) -> None:
        selected = self.profile(
            "stable-profile",
            priority=10,
            dimensions={"mold_type": "three_plate"},
        )
        records = create_design_review_records(self.version)
        snapshot = records.review.resolution_snapshot.copy()
        self.profile(
            "newer-profile",
            priority=20,
            dimensions={"mold_type": "three_plate"},
        )

        records.review.refresh_from_db()
        later = resolve_rule_profile(self.version)

        self.assertEqual(records.review.profile, selected)
        self.assertEqual(records.review.resolution_snapshot, snapshot)
        self.assertEqual(later.profile.profile_key, "newer-profile")
