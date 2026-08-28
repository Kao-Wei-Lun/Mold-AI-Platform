import json

from django.core.management.base import BaseCommand, CommandError

from platform_core.demo_reset import DemoResetError, reset_demo_datasets


class Command(BaseCommand):
    help = "Preview or execute the bounded Demo canonical-dataset reset."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--confirm",
            default="",
            help="Required exact phrase for execution; omission performs a dry run.",
        )
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    def handle(self, *args, **options) -> None:
        try:
            result = reset_demo_datasets(
                confirmation=options["confirm"], dry_run=not bool(options["confirm"])
            )
        except DemoResetError as exc:
            raise CommandError(str(exc)) from exc
        payload = {
            "schema_version": "1.0",
            "mode": "datasets",
            "dry_run": result.dry_run,
            "counts": result.counts,
            "removed_storage_files": result.removed_storage_files,
            "removed_vector_points": result.removed_feature_points,
            "preserved": [
                "similarity profiles",
                "rule profiles and rule versions",
                "existing audit events",
                "environment files and tunnel profiles",
                "Git repository and Docker volumes",
            ],
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            state = "DRY RUN" if result.dry_run else "COMPLETED"
            self.stdout.write(f"Demo datasets reset: {state}")
            for name, count in result.counts.items():
                self.stdout.write(f"  {name}: {count}")
