import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from platform_core.cad_review import fit_threshold, merge_reviews, review_template, validate_holdout


class Command(BaseCommand):
    help = (
        "Offline human templates, judgments, development fit and holdout validation. No DB writes."
    )
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["template", "merge", "fit", "validate"])
        parser.add_argument("input", type=Path)
        parser.add_argument("--root", type=Path)
        parser.add_argument("--review", type=Path)
        parser.add_argument("--development", type=Path)
        parser.add_argument("--holdout", type=Path)
        parser.add_argument("--reviewer", default="")
        parser.add_argument(
            "--dataset",
            action="append",
            default=[],
            help="Allowed online public dataset id for validated bundle",
        )
        parser.add_argument("--count", type=int, default=25)
        parser.add_argument("--output", type=Path, required=True)

    def handle(self, *args, **options):
        def read(path):
            if path is None or path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("Required input missing or exceeds 32 MiB")
            return json.loads(path.read_text(encoding="utf-8-sig"))

        try:
            action, data = options["action"], read(options["input"])
            if action in {"template", "merge"} and options["root"] is None:
                raise ValueError("--root is required")
            if action == "template":
                result = review_template(data, options["root"], count=options["count"])
            elif action == "merge":
                result = merge_reviews(data, read(options["review"]), options["root"])
            elif action == "fit":
                result = fit_threshold(data)
            else:
                development, holdout = read(options["development"]), read(options["holdout"])
                release = validate_holdout(
                    data,
                    development,
                    holdout,
                    reviewer=options["reviewer"],
                )
                result = {
                    "release": release,
                    "development_report": development,
                    "holdout_report": holdout,
                    "dataset_ids": options["dataset"],
                }
            with options["output"].open("x", encoding="utf-8") as target:
                json.dump(result, target, indent=2, ensure_ascii=False, allow_nan=False)
        except (ValueError, OSError, TypeError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Created {options['output']}. No production calibration activated.")
