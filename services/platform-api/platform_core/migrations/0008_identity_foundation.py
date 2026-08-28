import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


ROLE_CATALOG = {
    "viewer": (
        "Viewer",
        ["public-demo:read"],
    ),
    "data_editor": (
        "Data Editor",
        ["public-demo:read", "public-demo:write"],
    ),
    "data_steward": (
        "Data Steward",
        ["public-demo:read", "public-demo:write"],
    ),
    "mold_engineer": (
        "Mold Engineer",
        ["public-demo:read", "public-demo:write"],
    ),
    "rule_owner": (
        "Rule Owner",
        ["public-demo:read", "public-demo:write"],
    ),
    "technical_reviewer": (
        "Technical Reviewer",
        ["public-demo:read", "public-demo:write"],
    ),
    "approver": (
        "Approver",
        ["public-demo:read", "public-demo:write"],
    ),
    "knowledge_curator": (
        "Knowledge Curator",
        ["public-demo:read", "public-demo:write"],
    ),
    "platform_admin": (
        "Platform Admin",
        ["public-demo:read", "public-demo:write", "identity:manage", "identity:audit"],
    ),
    "auditor": (
        "Auditor",
        ["public-demo:read", "identity:audit"],
    ),
}


def seed_identity_foundation(apps, schema_editor):
    AccountProfile = apps.get_model("platform_core", "AccountProfile")
    AccessRole = apps.get_model("platform_core", "AccessRole")
    DataScope = apps.get_model("platform_core", "DataScope")
    RoleAssignment = apps.get_model("platform_core", "RoleAssignment")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    scope, _ = DataScope.objects.get_or_create(
        code="public-demo",
        defaults={
            "name": "Public Synthetic Demo",
            "description": "Public and synthetic data used by the controlled Demo.",
            "classification": "public_demo",
        },
    )
    for code, (name, permissions) in ROLE_CATALOG.items():
        AccessRole.objects.update_or_create(
            code=code,
            defaults={"name": name, "permissions": permissions, "is_system": True},
        )

    admin_role = AccessRole.objects.get(code="platform_admin")
    for user in User.objects.all():
        AccountProfile.objects.get_or_create(user=user)
        if user.is_superuser:
            RoleAssignment.objects.get_or_create(
                user=user,
                role=admin_role,
                data_scope=scope,
                revoked_at=None,
                defaults={"reason": "Migrated existing superuser"},
            )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("platform_core", "0007_alter_artifact_kind_hmiextraction_hmiexport_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccessRole",
            fields=[
                ("code", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True)),
                ("permissions", models.JSONField(default=list)),
                ("is_system", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["code"]},
        ),
        migrations.CreateModel(
            name="DataScope",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("code", models.CharField(max_length=128, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("classification", models.CharField(default="public_demo", max_length=32)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["code"]},
        ),
        migrations.CreateModel(
            name="AccountProfile",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("display_name", models.CharField(blank=True, max_length=150)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("suspended", "Suspended"),
                            ("disabled", "Disabled"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("locale", models.CharField(default="zh-TW", max_length=16)),
                ("timezone", models.CharField(default="Asia/Taipei", max_length=64)),
                ("row_version", models.PositiveIntegerField(default=1)),
                ("disabled_at", models.DateTimeField(blank=True, null=True)),
                ("disable_reason", models.CharField(blank=True, max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "disabled_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="disabled_mold_ai_accounts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="mold_ai_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["user__username"]},
        ),
        migrations.CreateModel(
            name="RoleAssignment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("valid_from", models.DateTimeField(blank=True, null=True)),
                ("valid_to", models.DateTimeField(blank=True, null=True)),
                ("reason", models.CharField(max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revoke_reason", models.CharField(blank=True, max_length=512)),
                (
                    "data_scope",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assignments",
                        to="platform_core.datascope",
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="granted_mold_ai_roles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "revoked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="revoked_mold_ai_roles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "role",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assignments",
                        to="platform_core.accessrole",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="mold_ai_role_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["user__username", "role_id", "data_scope__code"]},
        ),
        migrations.AddConstraint(
            model_name="roleassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("revoked_at__isnull", True)),
                fields=("user", "role", "data_scope"),
                name="unique_active_role_assignment",
            ),
        ),
        migrations.RunPython(seed_identity_foundation, migrations.RunPython.noop),
    ]
