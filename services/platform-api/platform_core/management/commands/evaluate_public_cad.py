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
            "--policy", choices=["cosine-v2", "block-distance@1.0"], default="cosine-v2"
        )
        parser.add_argument("--top-k", type=int, default=5)
        parser.add_argument("--sample-count", type=int, default=1024)
        parser.add_argument("--threshold", type=float)

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
            )
        except (ValueError, OSError, TypeError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
        if report["failures"]:
            raise CommandError("Evaluation incomplete; see parse failures in report")
