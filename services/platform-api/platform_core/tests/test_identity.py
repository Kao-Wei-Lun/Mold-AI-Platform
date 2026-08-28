from __future__ import annotations

import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings

from platform_core.identity import ensure_account_profile
from platform_core.models import AccessRole, AccountProfile, AuditEvent, DataScope, RoleAssignment

STRONG_PASSWORD = "Mold-Demo-Identity-2026!"


def create_account(username: str, role_code: str):
    user = get_user_model().objects.create_user(username=username, password=STRONG_PASSWORD)
    profile = ensure_account_profile(user)
    RoleAssignment.objects.create(
        user=user,
        role=AccessRole.objects.get(code=role_code),
        data_scope=DataScope.objects.get(code="public-demo"),
        granted_by=user,
        reason="Identity test setup",
    )
    return user, profile


@override_settings(DEMO_AUTH_MODE="local")
class LocalIdentityTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)

    def csrf_token(self) -> str:
        response = self.client.get("/api/v1/auth/csrf")
        self.assertEqual(response.status_code, 200)
        return response.json()["csrf_token"]

    def login(self, username: str, password: str = STRONG_PASSWORD):
        token = self.csrf_token()
        return self.client.post(
            "/api/v1/auth/login",
            {"username": username, "password": password},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

    def session_csrf_token(self) -> str:
        return self.client.cookies["csrftoken"].value

    def test_login_requires_csrf_and_returns_stable_account_context(self) -> None:
        user, profile = create_account("engineer", "mold_engineer")

        missing_csrf = self.client.post(
            "/api/v1/auth/login",
            {"username": user.username, "password": STRONG_PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(missing_csrf.json()["error"]["code"], "CSRF_FAILED")

        response = self.login(user.username)

        self.assertEqual(response.status_code, 200)
        account = response.json()["account"]
        self.assertEqual(account["id"], str(profile.id))
        self.assertEqual(account["roles"], ["mold_engineer"])
        self.assertEqual(account["data_scopes"], ["public-demo"])
        self.assertIn("public-demo:write", account["permissions"])
        me = self.client.get("/api/v1/auth/me")
        self.assertTrue(me.json()["authenticated"])
        self.assertTrue(
            AuditEvent.objects.filter(event_type="identity.login_succeeded.v1").exists()
        )

    def test_viewer_can_read_but_cannot_write(self) -> None:
        user, _ = create_account("viewer", "viewer")
        self.assertEqual(self.login(user.username).status_code, 200)

        read = self.client.get("/api/v1/system/info")
        denied = self.client.post(
            "/api/v1/assistant/messages",
            {"message": "hello", "context": {"context_version": "1.0"}},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.session_csrf_token(),
        )

        self.assertEqual(read.status_code, 200)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["code"], "PERMISSION_SCOPE_REQUIRED")

    @override_settings(LOCAL_AUTH_MAX_FAILURES=2, LOCAL_AUTH_LOCK_SECONDS=60)
    def test_failed_login_is_rate_limited_without_logging_password(self) -> None:
        create_account("limited", "viewer")
        first = self.login("limited", "wrong-password")
        second = self.login("limited", "wrong-password")
        limited = self.login("limited", STRONG_PASSWORD)

        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 401)
        self.assertEqual(limited.status_code, 429)
        self.assertNotIn("wrong-password", str(list(AuditEvent.objects.values("detail"))))

    def test_platform_admin_manages_accounts_with_optimistic_locking_and_audit(self) -> None:
        admin, _ = create_account("admin", "platform_admin")
        self.assertEqual(self.login(admin.username).status_code, 200)
        csrf = self.session_csrf_token()

        created = self.client.post(
            "/api/v1/admin/users",
            {
                "username": "alice",
                "email": "alice@example.test",
                "display_name": "Alice",
                "password": STRONG_PASSWORD,
                "role_code": "data_editor",
                "scope_code": "public-demo",
                "reason": "Demo data editor",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(created.status_code, 201)
        account = created.json()
        self.assertEqual(account["roles"], ["data_editor"])

        conflict = self.client.patch(
            f"/api/v1/admin/users/{account['id']}",
            {"row_version": 999, "display_name": "Changed"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(conflict.status_code, 409)

        updated = self.client.patch(
            f"/api/v1/admin/users/{account['id']}",
            {"row_version": account["row_version"], "display_name": "Alice Chen"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["display_name"], "Alice Chen")

        disabled = self.client.post(
            f"/api/v1/admin/users/{account['id']}/disable",
            {"reason": "Access no longer required"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json()["account"]["status"], "disabled")
        self.assertFalse(get_user_model().objects.get(username="alice").is_active)
        self.assertTrue(
            AuditEvent.objects.filter(event_type="identity.account_created.v1").exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(event_type="identity.account_disabled.v1").exists()
        )

    def test_non_admin_cannot_access_identity_admin_api(self) -> None:
        viewer, _ = create_account("not-admin", "viewer")
        self.assertEqual(self.login(viewer.username).status_code, 200)

        response = self.client.get("/api/v1/admin/users")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "ACCESS_DENIED")

    def test_suspended_account_session_is_revoked(self) -> None:
        admin, _ = create_account("suspending-admin", "platform_admin")
        target, profile = create_account("target", "viewer")
        target_client = Client(enforce_csrf_checks=True)
        target_token = target_client.get("/api/v1/auth/csrf").json()["csrf_token"]
        self.assertEqual(
            target_client.post(
                "/api/v1/auth/login",
                {"username": target.username, "password": STRONG_PASSWORD},
                content_type="application/json",
                HTTP_X_CSRFTOKEN=target_token,
            ).status_code,
            200,
        )
        self.assertEqual(self.login(admin.username).status_code, 200)
        suspended = self.client.post(
            f"/api/v1/admin/users/{profile.id}/suspend",
            {"reason": "Temporary access review"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.session_csrf_token(),
        )

        self.assertEqual(suspended.status_code, 200)
        self.assertGreaterEqual(suspended.json()["revoked_sessions"], 1)
        rejected = target_client.get("/api/v1/system/info")
        self.assertEqual(rejected.status_code, 401)
        self.assertEqual(rejected.json()["error"]["code"], "AUTH_SESSION_REQUIRED")


class BootstrapLocalAdminTests(TestCase):
    def test_bootstrap_is_one_time_and_does_not_persist_password(self) -> None:
        output = StringIO()
        with patch.dict(os.environ, {"MOLD_AI_BOOTSTRAP_PASSWORD": STRONG_PASSWORD}):
            call_command(
                "bootstrap_local_admin",
                username="bootstrap-admin",
                email="admin@example.test",
                display_name="Demo Administrator",
                stdout=output,
            )

        user = get_user_model().objects.get(username="bootstrap-admin")
        profile = AccountProfile.objects.get(user=user)
        self.assertTrue(user.check_password(STRONG_PASSWORD))
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(RoleAssignment.objects.filter(user=user, role_id="platform_admin").exists())
        self.assertIn("Created local Platform Admin", output.getvalue())
        self.assertNotIn(STRONG_PASSWORD, str(AuditEvent.objects.get().detail))
        self.assertEqual(profile.status, AccountProfile.Status.ACTIVE)

        with patch.dict(os.environ, {"MOLD_AI_BOOTSTRAP_PASSWORD": STRONG_PASSWORD}):
            with self.assertRaisesMessage(CommandError, "bootstrap is closed"):
                call_command("bootstrap_local_admin", username="second-admin")
