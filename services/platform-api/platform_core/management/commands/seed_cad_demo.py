from django.core.management.base import BaseCommand, CommandError

from platform_core.cad_fixtures import CADFixtureValidationError, seed_curated_cad_demo


class Command(BaseCommand):
    help = "Idempotently reconcile and verify the versioned curated CAD Demo corpus."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--verify-only",
            action="store_true",
            help="Check the existing corpus without creating or repairing records.",
        )

    def handle(self, *args, **options) -> None:
        try:
            result = seed_curated_cad_demo(verify_only=options["verify_only"])
        except CADFixtureValidationError as exc:
            raise CommandError(str(exc)) from exc
        mode = "verified" if options["verify_only"] else "ready"
        self.stdout.write(
            self.style.SUCCESS(
                f"Curated CAD {mode}: dataset={result.dataset_id}@{result.dataset_version}, "
                f"created={result.created}, existing={result.existing}, "
                f"reconciled={result.reconciled}, fixtures={result.verified}, "
                f"error_controls={result.error_controls_verified}, "
                f"similarity_golden={result.golden_similarity_verified}, "
                f"review_golden={result.golden_review_verified}, "
                f"manifest_sha256={result.manifest_sha256}"
            )
        )
