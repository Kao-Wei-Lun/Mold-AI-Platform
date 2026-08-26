from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from platform_core.security import security_preflight_payload


class Command(BaseCommand):
    help = "Evaluate the non-secret Demo release security configuration."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit unsuccessfully unless every external Demo release check passes.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit the complete machine-readable readiness document.",
        )

    def handle(self, *args, **options) -> None:
        request = RequestFactory().get("/api/v1/security/preflight", secure=True)
        payload = security_preflight_payload(request)
        failed = sorted(name for name, passed in payload["checks"].items() if not passed)

        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            status = "READY" if payload["production_ready"] else "NOT READY"
            self.stdout.write(f"Demo external release: {status}")
            self.stdout.write("Failed checks: " + (", ".join(failed) if failed else "none"))
            self.stdout.write(
                "This preflight never validates an OpenAI account, workspace policy, or OAuth flow."
            )

        if options["strict"] and not payload["production_ready"]:
            raise CommandError("Demo external release preflight failed.")
