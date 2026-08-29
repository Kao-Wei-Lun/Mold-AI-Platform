import uuid

import django.db.models.deletion
from django.db import migrations, models


def add_enterprise_permissions(apps, schema_editor):
    AccessRole = apps.get_model("platform_core", "AccessRole")
    for role in AccessRole.objects.all():
        permissions = list(role.permissions)
        if "enterprise:read" not in permissions:
            permissions.append("enterprise:read")
        if role.code in {"data_steward", "platform_admin"}:
            for permission in ("enterprise:manage", "bulk:manage"):
                if permission not in permissions:
                    permissions.append(permission)
        role.permissions = permissions
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("platform_core", "0014_history_centers")]

    operations = [
        migrations.CreateModel(
            name="EnterpriseDataPolicy",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "connector_mode",
                    models.CharField(
                        choices=[("public_demo", "Public Demo"), ("company", "Company connector")],
                        default="public_demo",
                        max_length=24,
                    ),
                ),
                ("retention_days", models.PositiveIntegerField(default=2555)),
                ("legal_hold", models.BooleanField(default=False)),
                ("legal_hold_reason", models.CharField(blank=True, max_length=512)),
                ("dlp_enabled", models.BooleanField(default=True)),
                ("export_allowed", models.BooleanField(default=True)),
                ("siem_enabled", models.BooleanField(default=False)),
                ("siem_destination", models.CharField(blank=True, max_length=255)),
                ("index_namespace", models.CharField(max_length=128)),
                ("cache_namespace", models.CharField(max_length=128)),
                ("row_version", models.PositiveIntegerField(default=1)),
                ("updated_by", models.CharField(default="system", max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "scope",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="enterprise_policy",
                        to="platform_core.datascope",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="BulkImportBatch",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("domain", models.CharField(max_length=32)),
                ("source_name", models.CharField(max_length=255)),
                ("idempotency_key", models.CharField(max_length=255, unique=True)),
                ("records", models.JSONField(default=list)),
                ("field_mapping", models.JSONField(default=dict)),
                ("validation_result", models.JSONField(default=dict)),
                ("reconciliation", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("validated", "Validated"),
                            ("committed", "Committed"),
                            ("failed", "Failed"),
                        ],
                        default="validated",
                        max_length=16,
                    ),
                ),
                ("created_by", models.CharField(max_length=128)),
                ("committed_by", models.CharField(blank=True, max_length=128)),
                ("committed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "scope",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="import_batches",
                        to="platform_core.datascope",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="BulkArchiveOperation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("domain", models.CharField(max_length=32)),
                ("record_ids", models.JSONField(default=list)),
                ("dry_run", models.BooleanField(default=True)),
                ("status", models.CharField(default="validated", max_length=24)),
                ("result", models.JSONField(default=dict)),
                ("reason", models.CharField(max_length=512)),
                ("actor_id", models.CharField(max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "scope",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="archive_operations",
                        to="platform_core.datascope",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="bulkimportbatch",
            index=models.Index(
                fields=["scope", "status", "created_at"], name="bulk_scope_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="artifact",
            index=models.Index(
                fields=["dataset_id", "lifecycle_status", "created_at"],
                name="artifact_dataset_life_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="trialcase",
            index=models.Index(
                fields=["classification", "lifecycle_status", "created_at"],
                name="trial_class_life_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="caestudy",
            index=models.Index(
                fields=["classification", "lifecycle_status", "created_at"],
                name="cae_class_life_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["event_type", "created_at"], name="audit_type_created_idx"),
        ),
        migrations.AddIndex(
            model_name="knowledgedocument",
            index=models.Index(
                fields=["classification", "publication_status", "created_at"],
                name="knowledge_class_pub_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="ruleprofile",
            index=models.Index(
                fields=["profile_key", "workflow_status", "created_at"],
                name="rule_key_workflow_idx",
            ),
        ),
        migrations.RunPython(add_enterprise_permissions, migrations.RunPython.noop),
    ]
