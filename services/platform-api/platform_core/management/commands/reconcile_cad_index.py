import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from platform_core.cad_index_reconciliation import inspect_orphans, remove_confirmed_orphans


class Command(BaseCommand):
    help = (
        "Preview orphan public v2 points; --apply requires an expected count and new backup file."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dataset", required=True)
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--expected-orphan-count", type=int)

    def handle(self, *args, **options):
        try:
            if options["output"].exists():
                raise ValueError("Output must be a new backup file")
            report = inspect_orphans(options["dataset"])
            if options["apply"] and options["expected_orphan_count"] != report["orphan_count"]:
                raise ValueError("--expected-orphan-count must equal the current dry-run count")
            # Backup closes successfully BEFORE any deletion; never overwrite a previous receipt.
            with options["output"].open("x", encoding="utf-8") as target:
                json.dump(report, target, indent=2, allow_nan=False)
            removed = (
                remove_confirmed_orphans(report, options["expected_orphan_count"])
                if options["apply"]
                else 0
            )
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps(
                {
                    "scanned": report["scanned"],
                    "retained": report["retained_count"],
                    "orphans": report["orphan_count"],
                    "removed_index_points": removed,
                    "database_records_deleted": 0,
                    "backup": str(options["output"]),
                }
            )
        )
