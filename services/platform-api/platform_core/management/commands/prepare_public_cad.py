from pathlib import Path

import httpx
from django.core.management.base import BaseCommand, CommandError

from platform_core.public_cad_corpus import prepare_mfcad_corpus


class Command(BaseCommand):
    help = "Download the checksum-pinned 12-model MFCAD smoke corpus (not into the business DB)."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--root", type=Path, required=True)
        parser.add_argument(
            "--extended", action="store_true", help="Use the separate 100-model pinned corpus"
        )

    def handle(self, *args, **options):
        try:
            result = prepare_mfcad_corpus(options["root"], extended=options["extended"])
        except (ValueError, OSError, httpx.HTTPError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Prepared {len(result['models'])} controlled-only public CAD models.")
        self.stdout.write("No business data imported. No human-labelled quality gate has passed.")
