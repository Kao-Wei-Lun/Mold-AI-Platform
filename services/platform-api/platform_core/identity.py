from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db.models import Q
from django.utils import timezone

from .models import AccountProfile, AuditEvent, RoleAssignment

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

PLATFORM_ADMIN_PERMISSIONS = {
    "public-demo:read",
    "public-demo:write",
    "identity:manage",
    "identity:audit",
    "master-data:read",
    "master-data:manage",
}


def ensure_account_profile(user: AbstractBaseUser) -> AccountProfile:
    profile, _ = AccountProfile.objects.get_or_create(
        user=user,
        defaults={"display_name": user.get_full_name()},
    )
    return profile


def active_role_assignments(user: AbstractBaseUser) -> list[RoleAssignment]:
    now = timezone.now()
    return list(
        RoleAssignment.objects.select_related("role", "data_scope")
        .filter(
            user=user,
            revoked_at__isnull=True,
            role__is_active=True,
            data_scope__is_active=True,
        )
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=now))
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=now))
        .order_by("role_id", "data_scope__code")
    )


def identity_context(user: AbstractBaseUser) -> dict[str, object]:
    profile = ensure_account_profile(user)
    assignments = active_role_assignments(user)
    roles = sorted({assignment.role_id for assignment in assignments})
    permissions = {
        permission
        for assignment in assignments
        for permission in assignment.role.permissions
        if isinstance(permission, str)
    }
    data_scopes = sorted({assignment.data_scope.code for assignment in assignments})
    if user.is_superuser:
        roles = sorted(set(roles) | {"platform_admin"})
        permissions.update(PLATFORM_ADMIN_PERMISSIONS)
        if not data_scopes:
            data_scopes = ["public-demo"]
    return {
        "actor_id": str(profile.id),
        "profile": profile,
        "roles": roles,
        "permissions": permissions,
        "data_scopes": data_scopes,
        "assignments": assignments,
    }


def account_payload(user: AbstractBaseUser) -> dict[str, object]:
    context = identity_context(user)
    profile = context["profile"]
    assert isinstance(profile, AccountProfile)
    return {
        "id": str(profile.id),
        "username": user.get_username(),
        "email": user.email,
        "display_name": profile.display_name or user.get_full_name() or user.get_username(),
        "status": profile.status,
        "locale": profile.locale,
        "timezone": profile.timezone,
        "row_version": profile.row_version,
        "roles": context["roles"],
        "permissions": sorted(context["permissions"]),
        "data_scopes": context["data_scopes"],
        "role_assignments": [
            {
                "id": str(assignment.id),
                "role_code": assignment.role_id,
                "role_name": assignment.role.name,
                "scope_code": assignment.data_scope.code,
                "scope_name": assignment.data_scope.name,
                "valid_from": (
                    assignment.valid_from.isoformat() if assignment.valid_from else None
                ),
                "valid_to": assignment.valid_to.isoformat() if assignment.valid_to else None,
            }
            for assignment in context["assignments"]
        ],
        "last_login_at": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.date_joined.isoformat(),
    }


def audit_identity_event(
    event_type: str,
    *,
    actor_id: str,
    target_refs: list[str],
    detail: dict[str, object],
) -> AuditEvent:
    canonical = json.dumps(
        {
            "event_type": event_type,
            "actor_id": actor_id,
            "target_refs": target_refs,
            "detail": detail,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return AuditEvent.objects.create(
        event_type=event_type,
        actor_id=actor_id,
        target_refs=target_refs,
        detail=detail,
        payload_hash=hashlib.sha256(canonical.encode()).hexdigest(),
    )


def revoke_user_sessions(user: AbstractBaseUser) -> int:
    revoked = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
            session.delete()
            revoked += 1
    return revoked


def username_exists(username: str) -> bool:
    return get_user_model().objects.filter(username__iexact=username).exists()
