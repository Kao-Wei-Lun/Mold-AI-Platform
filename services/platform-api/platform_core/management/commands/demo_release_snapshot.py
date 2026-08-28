import json

from django.core.management.base import BaseCommand, CommandError

from platform_core.operations import release_snapshot_payload


class Command(BaseCommand):
    help = "Emit a sanitized, read-only Demo release and backup metadata snapshot."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail unless dependencies and the curated CAD reconciliation are ready.",
        )

    def handle(self, *args, **options) -> None:
        payload = release_snapshot_payload()
        curated = payload["datasets"]["curated_cad"]
        if options["strict"] and (
            payload["readiness"]["status"] != "ok" or not curated["reconciled"]
        ):
            raise CommandError("Demo release snapshot is not ready.")
        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        self.stdout.write(
            "Demo release snapshot: "
            f"app={payload['application']['version']}, "
            f"curated_cad={curated['ready']}/{curated['expected']}, "
            f"indexed={curated['indexed']}, artifacts={payload['records']['artifacts']}"
        )
