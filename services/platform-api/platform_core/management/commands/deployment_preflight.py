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
        parser.add_argument(
            "--profile",
            choices=("release", "quick-tunnel"),
            default="release",
            help="Readiness profile to evaluate.",
        )

    def handle(self, *args, **options) -> None:
        request = RequestFactory().get("/api/v1/security/preflight", secure=True)
        payload = security_preflight_payload(request)
        profile = options["profile"]
        selected_checks = (
            payload["quick_tunnel"]["checks"] if profile == "quick-tunnel" else payload["checks"]
        )
        ready = (
            payload["quick_tunnel"]["ready"]
            if profile == "quick-tunnel"
            else payload["production_ready"]
        )
        failed = sorted(name for name, passed in selected_checks.items() if not passed)

        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            status = "READY" if ready else "NOT READY"
            self.stdout.write(f"Demo {profile}: {status}")
            self.stdout.write("Failed checks: " + (", ".join(failed) if failed else "none"))
            self.stdout.write(
                "This preflight never validates an OpenAI account, workspace policy, or OAuth flow."
            )

        if options["strict"] and not ready:
            raise CommandError(f"Demo {profile} preflight failed.")
