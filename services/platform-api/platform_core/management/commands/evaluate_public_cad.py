import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from platform_core.cad_evaluation import evaluate_corpus


class Command(BaseCommand):
    help = "Evaluate a local, provenance-checked public CAD corpus without database writes."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("manifest", type=Path)
        parser.add_argument("--root", type=Path, required=True)
        parser.add_argument("--split", choices=["development", "holdout"], default="holdout")
        parser.add_argument(
            "--policy",
            choices=["cosine-v2", "block-distance@1.0", "cpu-surface-verification@2.0"],
            default="cosine-v2",
        )
        parser.add_argument("--top-k", type=int, default=5)
        parser.add_argument("--sample-count", type=int, default=1024)
        parser.add_argument("--threshold", type=float)
        parser.add_argument("--query-limit", type=int)
        parser.add_argument("--coarse-limit", type=int, default=25)
        parser.add_argument("--output", type=Path, help="Create a new JSON report; never overwrite")

    def handle(self, *args, **options):
        try:
            manifest = json.loads(options["manifest"].read_text(encoding="utf-8-sig"))
            report = evaluate_corpus(
                manifest,
                options["root"],
                split=options["split"],
                policy=options["policy"],
                k=options["top_k"],
                sample_count=options["sample_count"],
                threshold=options["threshold"],
                query_limit=options["query_limit"],
                coarse_limit=options["coarse_limit"],
            )
        except (ValueError, OSError, TypeError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        rendered = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False)
        if options["output"]:
            try:
                with options["output"].open("x", encoding="utf-8") as target:
                    target.write(rendered)
            except OSError as exc:
                raise CommandError(f"Cannot create report: {exc}") from exc
            self.stdout.write(f"Report created: {options['output']}")
        else:
            self.stdout.write(rendered)
        if report["failures"]:
            raise CommandError("Evaluation incomplete; see parse/comparison failures in report")
