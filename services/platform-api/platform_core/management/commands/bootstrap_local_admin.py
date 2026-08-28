from __future__ import annotations

import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from platform_core.identity import audit_identity_event, ensure_account_profile
from platform_core.models import AccessRole, DataScope, RoleAssignment


class Command(BaseCommand):
    help = "Create the first local Platform Admin exactly once; never accepts a password argument."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")
        parser.add_argument("--display-name", default="")

    def handle(self, *args, **options) -> None:
        if RoleAssignment.objects.filter(
            role_id="platform_admin",
            revoked_at__isnull=True,
            user__is_active=True,
        ).exists():
            raise CommandError("A local Platform Admin already exists; bootstrap is closed.")

        username = str(options["username"]).strip()
        email = str(options["email"]).strip()
        display_name = str(options["display_name"]).strip()
        if not username:
            raise CommandError("A non-empty username is required.")

        password = os.getenv("MOLD_AI_BOOTSTRAP_PASSWORD") or getpass.getpass(
            "New local administrator password: "
        )
        confirmation = os.getenv("MOLD_AI_BOOTSTRAP_PASSWORD") or getpass.getpass(
            "Confirm password: "
        )
        if not password or password != confirmation:
            raise CommandError("Passwords do not match.")

        User = get_user_model()
        candidate = User(username=username, email=email)
        try:
            validate_password(password, candidate)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        if User.objects.filter(username__iexact=username).exists():
            raise CommandError("The username already exists; bootstrap will not merge identities.")

        role = AccessRole.objects.filter(code="platform_admin", is_active=True).first()
        scope = DataScope.objects.filter(code="public-demo", is_active=True).first()
        if role is None or scope is None:
            raise CommandError("Identity seed records are missing; run migrations first.")

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=True,
            )
            profile = ensure_account_profile(user)
            profile.display_name = display_name
            profile.save(update_fields=["display_name", "updated_at"])
            RoleAssignment.objects.create(
                user=user,
                role=role,
                data_scope=scope,
                granted_by=user,
                reason="One-time local administrator bootstrap",
            )
            audit_identity_event(
                "identity.bootstrap_completed.v1",
                actor_id=str(profile.id),
                target_refs=[f"account:{profile.id}"],
                detail={"role": role.code, "scope": scope.code},
            )

        self.stdout.write(self.style.SUCCESS(f"Created local Platform Admin: {username}"))
