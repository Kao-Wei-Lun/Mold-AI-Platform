from __future__ import annotations

import hashlib

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .identity import (
    account_payload,
    audit_identity_event,
    ensure_account_profile,
    revoke_user_sessions,
    username_exists,
)
from .models import AccessRole, AccountProfile, DataScope, RoleAssignment


def _error(request: Request, code: str, message: str, http_status: int) -> Response:
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": False,
                "request_id": getattr(request._request, "mold_ai_request_id", ""),
            }
        },
        status=http_status,
    )


def _has_permission(request: Request, permission: str) -> bool:
    return permission in getattr(request._request, "mold_ai_permissions", set())


def _require_identity_admin(request: Request) -> Response | None:
    if _has_permission(request, "identity:manage"):
        return None
    return _error(
        request,
        "ACCESS_DENIED",
        "The account does not grant identity management permission.",
        status.HTTP_403_FORBIDDEN,
    )


def _request_actor(request: Request) -> str:
    return str(getattr(request._request, "mold_ai_actor_id", "anonymous"))


def _django_user(request: Request):
    return request._request.user


def _login_rate_key(request: Request, username: str) -> str:
    remote = request.META.get("REMOTE_ADDR", "unknown")
    digest = hashlib.sha256(f"{remote}|{username.casefold()}".encode()).hexdigest()
    return f"mold-ai:login-failures:{digest}"


def _record_login_failure(key: str) -> int:
    if cache.add(key, 1, timeout=settings.LOCAL_AUTH_LOCK_SECONDS):
        return 1
    try:
        return int(cache.incr(key))
    except ValueError:
        cache.set(key, 1, timeout=settings.LOCAL_AUTH_LOCK_SECONDS)
        return 1


class CsrfTokenView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response({"csrf_token": get_token(request._request)})


class LocalLoginView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        if settings.DEMO_AUTH_MODE != "local":
            return _error(
                request,
                "LOCAL_AUTH_DISABLED",
                "Local account authentication is not enabled.",
                status.HTTP_409_CONFLICT,
            )
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", ""))
        if not username or not password or len(username) > 150 or len(password) > 4096:
            return _error(
                request,
                "AUTH_CREDENTIALS_INVALID",
                "The username or password is invalid.",
                status.HTTP_401_UNAUTHORIZED,
            )

        rate_key = _login_rate_key(request, username)
        failures = int(cache.get(rate_key, 0))
        if failures >= settings.LOCAL_AUTH_MAX_FAILURES:
            audit_identity_event(
                "identity.login_rate_limited.v1",
                actor_id="unauthenticated",
                target_refs=["auth:local"],
                detail={
                    "username_hash": hashlib.sha256(username.casefold().encode()).hexdigest(),
                    "request_id": getattr(request._request, "mold_ai_request_id", ""),
                },
            )
            return _error(
                request,
                "AUTH_RATE_LIMITED",
                "Too many failed sign-in attempts. Try again later.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )

        user = authenticate(request=request._request, username=username, password=password)
        if user is None:
            _record_login_failure(rate_key)
            audit_identity_event(
                "identity.login_failed.v1",
                actor_id="unauthenticated",
                target_refs=["auth:local"],
                detail={
                    "username_hash": hashlib.sha256(username.casefold().encode()).hexdigest(),
                    "request_id": getattr(request._request, "mold_ai_request_id", ""),
                },
            )
            return _error(
                request,
                "AUTH_CREDENTIALS_INVALID",
                "The username or password is invalid.",
                status.HTTP_401_UNAUTHORIZED,
            )

        profile = ensure_account_profile(user)
        if profile.status != AccountProfile.Status.ACTIVE:
            return _error(
                request,
                "ACCOUNT_NOT_ACTIVE",
                "The local account is not active.",
                status.HTTP_403_FORBIDDEN,
            )
        cache.delete(rate_key)
        login(request._request, user)
        request._request.session.cycle_key()
        payload = account_payload(user)
        audit_identity_event(
            "identity.login_succeeded.v1",
            actor_id=str(profile.id),
            target_refs=[f"account:{profile.id}"],
            detail={"request_id": getattr(request._request, "mold_ai_request_id", "")},
        )
        return Response({"authenticated": True, "account": payload})


class LocalLogoutView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        actor_id = "anonymous"
        django_user = _django_user(request)
        if django_user.is_authenticated:
            actor_id = str(ensure_account_profile(django_user).id)
        logout(request._request)
        audit_identity_event(
            "identity.logout.v1",
            actor_id=actor_id,
            target_refs=[f"account:{actor_id}"],
            detail={"request_id": getattr(request._request, "mold_ai_request_id", "")},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentAccountView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        django_user = _django_user(request)
        if django_user.is_authenticated:
            return Response(
                {
                    "authenticated": True,
                    "authentication_method": "session",
                    "account": account_payload(django_user),
                }
            )
        return Response(
            {
                "authenticated": False,
                "authentication_method": (
                    "bearer_gateway" if settings.DEMO_AUTH_MODE == "required" else "none"
                ),
                "account": None,
            }
        )


class AccountListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        denied = _require_identity_admin(request)
        if denied:
            return denied
        users = get_user_model().objects.select_related("mold_ai_profile").order_by("username")
        return Response({"results": [account_payload(user) for user in users[:100]]})

    def post(self, request: Request) -> Response:
        denied = _require_identity_admin(request)
        if denied:
            return denied
        username = str(request.data.get("username", "")).strip()
        email = str(request.data.get("email", "")).strip()
        display_name = str(request.data.get("display_name", "")).strip()
        password = str(request.data.get("password", ""))
        role_code = str(request.data.get("role_code", "viewer")).strip()
        scope_code = str(request.data.get("scope_code", "public-demo")).strip()
        reason = str(request.data.get("reason", "")).strip()
        if not username or not password or not reason:
            return _error(
                request,
                "VALIDATION_REQUIRED_FIELDS",
                "username, password and reason are required.",
                status.HTTP_400_BAD_REQUEST,
            )
        if username_exists(username):
            return _error(
                request,
                "IDENTITY_CONFLICT",
                "The username is already in use.",
                status.HTTP_409_CONFLICT,
            )
        if email:
            try:
                validate_email(email)
            except ValidationError:
                return _error(
                    request,
                    "VALIDATION_EMAIL",
                    "The email address is invalid.",
                    status.HTTP_400_BAD_REQUEST,
                )
        role = AccessRole.objects.filter(code=role_code, is_active=True).first()
        scope = DataScope.objects.filter(code=scope_code, is_active=True).first()
        if role is None or scope is None:
            return _error(
                request,
                "VALIDATION_ROLE_SCOPE",
                "The selected role or data scope is invalid.",
                status.HTTP_400_BAD_REQUEST,
            )
        User = get_user_model()
        candidate = User(username=username, email=email)
        try:
            validate_password(password, candidate)
        except ValidationError as exc:
            return _error(
                request,
                "VALIDATION_PASSWORD",
                " ".join(exc.messages),
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password)
                profile = ensure_account_profile(user)
                profile.display_name = display_name
                profile.save(update_fields=["display_name", "updated_at"])
                RoleAssignment.objects.create(
                    user=user,
                    role=role,
                    data_scope=scope,
                    granted_by=_django_user(request),
                    reason=reason,
                )
                audit_identity_event(
                    "identity.account_created.v1",
                    actor_id=_request_actor(request),
                    target_refs=[f"account:{profile.id}"],
                    detail={"role": role.code, "scope": scope.code, "reason": reason},
                )
        except IntegrityError:
            return _error(
                request,
                "IDENTITY_CONFLICT",
                "The account conflicts with an existing identity.",
                status.HTTP_409_CONFLICT,
            )
        return Response(account_payload(user), status=status.HTTP_201_CREATED)


class AccountDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, account_id: str) -> Response:
        denied = _require_identity_admin(request)
        if denied:
            return denied
        profile = AccountProfile.objects.select_related("user").filter(id=account_id).first()
        if profile is None:
            return _error(request, "NOT_FOUND", "Account not found.", status.HTTP_404_NOT_FOUND)
        return Response(account_payload(profile.user))

    def patch(self, request: Request, account_id: str) -> Response:
        denied = _require_identity_admin(request)
        if denied:
            return denied
        profile = AccountProfile.objects.select_related("user").filter(id=account_id).first()
        if profile is None:
            return _error(request, "NOT_FOUND", "Account not found.", status.HTTP_404_NOT_FOUND)
        try:
            row_version = int(request.data.get("row_version"))
        except (TypeError, ValueError):
            return _error(
                request,
                "ROW_VERSION_REQUIRED",
                "row_version is required.",
                status.HTTP_400_BAD_REQUEST,
            )
        if row_version != profile.row_version:
            return _error(
                request,
                "CONCURRENT_MODIFICATION",
                "The account was changed by another request.",
                status.HTTP_409_CONFLICT,
            )

        display_name = str(request.data.get("display_name", profile.display_name)).strip()
        locale = str(request.data.get("locale", profile.locale)).strip()
        account_timezone = str(request.data.get("timezone", profile.timezone)).strip()
        email = str(request.data.get("email", profile.user.email)).strip()
        if email:
            try:
                validate_email(email)
            except ValidationError:
                return _error(
                    request,
                    "VALIDATION_EMAIL",
                    "The email address is invalid.",
                    status.HTTP_400_BAD_REQUEST,
                )
        with transaction.atomic():
            profile.display_name = display_name
            profile.locale = locale[:16]
            profile.timezone = account_timezone[:64]
            profile.row_version += 1
            profile.user.email = email
            profile.user.save(update_fields=["email"])
            profile.save(
                update_fields=["display_name", "locale", "timezone", "row_version", "updated_at"]
            )
            audit_identity_event(
                "identity.account_updated.v1",
                actor_id=_request_actor(request),
                target_refs=[f"account:{profile.id}"],
                detail={"row_version": profile.row_version},
            )
        return Response(account_payload(profile.user))


class AccountStateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, account_id: str, action: str) -> Response:
        denied = _require_identity_admin(request)
        if denied:
            return denied
        profile = AccountProfile.objects.select_related("user").filter(id=account_id).first()
        if profile is None:
            return _error(request, "NOT_FOUND", "Account not found.", status.HTTP_404_NOT_FOUND)
        django_user = _django_user(request)
        if django_user.pk == profile.user_id and action in {"suspend", "disable"}:
            return _error(
                request,
                "SELF_LOCKOUT_FORBIDDEN",
                "An administrator cannot suspend or disable their own account.",
                status.HTTP_409_CONFLICT,
            )
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            return _error(
                request,
                "VALIDATION_REASON_REQUIRED",
                "A reason is required.",
                status.HTTP_400_BAD_REQUEST,
            )
        if action not in {"activate", "suspend", "disable", "revoke-sessions"}:
            return _error(request, "NOT_FOUND", "Action not found.", status.HTTP_404_NOT_FOUND)

        revoked_sessions = 0
        with transaction.atomic():
            if action == "activate":
                profile.status = AccountProfile.Status.ACTIVE
                profile.user.is_active = True
                profile.disabled_at = None
                profile.disabled_by = None
                profile.disable_reason = ""
            elif action in {"suspend", "disable"}:
                profile.status = (
                    AccountProfile.Status.SUSPENDED
                    if action == "suspend"
                    else AccountProfile.Status.DISABLED
                )
                profile.user.is_active = False
                profile.disabled_at = timezone.now()
                profile.disabled_by = django_user
                profile.disable_reason = reason
                revoked_sessions = revoke_user_sessions(profile.user)
            else:
                revoked_sessions = revoke_user_sessions(profile.user)
            profile.row_version += 1
            profile.user.save(update_fields=["is_active"])
            profile.save()
            event_types = {
                "activate": "identity.account_activated.v1",
                "suspend": "identity.account_suspended.v1",
                "disable": "identity.account_disabled.v1",
                "revoke-sessions": "identity.sessions_revoked.v1",
            }
            audit_identity_event(
                event_types[action],
                actor_id=_request_actor(request),
                target_refs=[f"account:{profile.id}"],
                detail={"reason": reason, "revoked_sessions": revoked_sessions},
            )
        return Response(
            {"account": account_payload(profile.user), "revoked_sessions": revoked_sessions}
        )


class IdentityCatalogView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        denied = _require_identity_admin(request)
        if denied:
            return denied
        return Response(
            {
                "roles": [
                    {
                        "code": role.code,
                        "name": role.name,
                        "description": role.description,
                        "permissions": role.permissions,
                    }
                    for role in AccessRole.objects.filter(is_active=True)
                ],
                "data_scopes": [
                    {
                        "id": str(scope.id),
                        "code": scope.code,
                        "name": scope.name,
                        "classification": scope.classification,
                    }
                    for scope in DataScope.objects.filter(is_active=True)
                ],
            }
        )


class RoleAssignmentCreateRevokeView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        denied = _require_identity_admin(request)
        if denied:
            return denied
        account_id = str(request.data.get("account_id", ""))
        role_code = str(request.data.get("role_code", ""))
        scope_code = str(request.data.get("scope_code", ""))
        reason = str(request.data.get("reason", "")).strip()
        profile = AccountProfile.objects.select_related("user").filter(id=account_id).first()
        role = AccessRole.objects.filter(code=role_code, is_active=True).first()
        scope = DataScope.objects.filter(code=scope_code, is_active=True).first()
        if profile is None or role is None or scope is None or not reason:
            return _error(
                request,
                "VALIDATION_ASSIGNMENT",
                "A valid account, role, scope and reason are required.",
                status.HTTP_400_BAD_REQUEST,
            )
        try:
            assignment = RoleAssignment.objects.create(
                user=profile.user,
                role=role,
                data_scope=scope,
                granted_by=_django_user(request),
                reason=reason,
            )
        except IntegrityError:
            return _error(
                request,
                "ROLE_ASSIGNMENT_CONFLICT",
                "The active role assignment already exists.",
                status.HTTP_409_CONFLICT,
            )
        audit_identity_event(
            "identity.role_assigned.v1",
            actor_id=_request_actor(request),
            target_refs=[f"account:{profile.id}", f"role-assignment:{assignment.id}"],
            detail={"role": role.code, "scope": scope.code, "reason": reason},
        )
        return Response({"id": str(assignment.id)}, status=status.HTTP_201_CREATED)

    def delete(self, request: Request, assignment_id: str) -> Response:
        denied = _require_identity_admin(request)
        if denied:
            return denied
        assignment = (
            RoleAssignment.objects.select_related("user__mold_ai_profile")
            .filter(
                id=assignment_id,
                revoked_at__isnull=True,
            )
            .first()
        )
        if assignment is None:
            return _error(request, "NOT_FOUND", "Assignment not found.", status.HTTP_404_NOT_FOUND)
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            return _error(
                request,
                "VALIDATION_REASON_REQUIRED",
                "A reason is required.",
                status.HTTP_400_BAD_REQUEST,
            )
        django_user = _django_user(request)
        if django_user.pk == assignment.user_id and assignment.role_id == "platform_admin":
            return _error(
                request,
                "SELF_LOCKOUT_FORBIDDEN",
                "An administrator cannot revoke their own platform administrator role.",
                status.HTTP_409_CONFLICT,
            )
        assignment.revoked_at = timezone.now()
        assignment.revoked_by = django_user
        assignment.revoke_reason = reason
        assignment.save(update_fields=["revoked_at", "revoked_by", "revoke_reason"])
        audit_identity_event(
            "identity.role_revoked.v1",
            actor_id=_request_actor(request),
            target_refs=[
                f"account:{assignment.user.mold_ai_profile.id}",
                f"role-assignment:{assignment.id}",
            ],
            detail={"role": assignment.role_id, "reason": reason},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
