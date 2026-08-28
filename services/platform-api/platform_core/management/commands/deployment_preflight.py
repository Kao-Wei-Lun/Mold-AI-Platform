from __future__ import annotations

import json

from django.conf import settings
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
        parser.add_argument(
            "--allow-local-admin-bootstrap",
            action="store_true",
            help=(
                "Allow quick-tunnel startup only when the sole failed check is the first "
                "local Platform Admin bootstrap. All other checks remain strict."
            ),
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
        bootstrap_pending = (
            options["allow_local_admin_bootstrap"]
            and profile == "quick-tunnel"
            and settings.DEMO_AUTH_MODE == "local"
            and failed == ["local_admin_configured"]
        )

        if options["json"]:
            payload["startup"] = {
                "ready": ready or bootstrap_pending,
                "local_admin_bootstrap_pending": bootstrap_pending,
            }
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            status = (
                "ADMIN BOOTSTRAP PENDING"
                if bootstrap_pending
                else ("READY" if ready else "NOT READY")
            )
            self.stdout.write(f"Demo {profile}: {status}")
            self.stdout.write("Failed checks: " + (", ".join(failed) if failed else "none"))
            self.stdout.write(
                "This preflight never validates an OpenAI account, workspace policy, or OAuth flow."
            )

        if options["strict"] and not ready and not bootstrap_pending:
            raise CommandError(f"Demo {profile} preflight failed.")
