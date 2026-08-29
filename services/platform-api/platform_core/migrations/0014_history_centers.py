import uuid

from django.db import migrations, models


def add_history_permissions(apps, schema_editor):
    AccessRole = apps.get_model("platform_core", "AccessRole")
    read_permissions = ("job:read", "audit:read", "lineage:read", "analysis:read")
    for role in AccessRole.objects.all():
        permissions = list(role.permissions)
        for permission in read_permissions:
            if permission not in permissions:
                permissions.append(permission)
        if role.code in {"mold_engineer", "data_steward", "platform_admin"}:
            for permission in ("job:cancel", "job:retry", "analysis:manage"):
                if permission not in permissions:
                    permissions.append(permission)
        if role.code in {"auditor", "platform_admin"} and "audit:export" not in permissions:
            permissions.append("audit:export")
        role.permissions = permissions
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("platform_core", "0013_history_mutation_versions")]

    operations = [
        migrations.CreateModel(
            name="HistoryRecordState",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("record_type", models.CharField(max_length=64)),
                ("record_id", models.UUIDField()),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("archived", "Archived")],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("row_version", models.PositiveIntegerField(default=1)),
                ("archive_reason", models.CharField(blank=True, max_length=512)),
                ("archived_by", models.CharField(blank=True, max_length=128)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="historyrecordstate",
            constraint=models.UniqueConstraint(
                fields=("record_type", "record_id"), name="unique_history_record_state"
            ),
        ),
        migrations.AddIndex(
            model_name="historyrecordstate",
            index=models.Index(fields=["record_type", "status"], name="history_type_status_idx"),
        ),
        migrations.RunPython(add_history_permissions, migrations.RunPython.noop),
    ]
