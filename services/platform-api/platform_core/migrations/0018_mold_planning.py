import uuid

import django.db.models.deletion
from django.db import migrations, models


ROLE_PERMISSIONS = {
    "viewer": {"mold-planning:read"},
    "mold_engineer": {
        "mold-planning:read",
        "mold-planning:create",
        "mold-planning:complete",
    },
    "technical_reviewer": {"mold-planning:read"},
    "approver": {"mold-planning:read", "mold-planning:complete"},
    "platform_admin": {
        "mold-planning:read",
        "mold-planning:create",
        "mold-planning:manage",
        "mold-planning:complete",
        "rules:override",
    },
    "auditor": {"mold-planning:read"},
}


def add_mold_planning_permissions(apps, schema_editor):
    AccessRole = apps.get_model("platform_core", "AccessRole")
    for role_code, added in ROLE_PERMISSIONS.items():
        role = AccessRole.objects.filter(code=role_code).first()
        if role is None:
            continue
        role.permissions = sorted(set(role.permissions or []) | added)
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("platform_core", "0017_ingestion_foundation")]

    operations = [
        migrations.CreateModel(
            name="MoldPlan",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("plan_code", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=120)),
                ("purpose", models.CharField(choices=[("new_mold", "New mold"), ("modification", "Modification"), ("design_change", "Design change"), ("trial_improvement", "Trial improvement"), ("other", "Other")], max_length=32)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("ready", "Ready"), ("completed", "Completed"), ("archived", "Archived")], default="draft", max_length=16)),
                ("owner_id", models.CharField(max_length=128)),
                ("classification", models.CharField(default="public_demo", max_length=32)),
                ("row_version", models.PositiveIntegerField(default=1)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("archive_reason", models.CharField(blank=True, max_length=512)),
                ("created_by", models.CharField(max_length=128)),
                ("updated_by", models.CharField(max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cad_artifact_version", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="mold_plans", to="platform_core.artifactversion")),
                ("mold", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mold_plans", to="platform_core.mold")),
                ("mold_revision", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mold_plans", to="platform_core.moldrevision")),
                ("part", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="mold_plans", to="platform_core.productpart")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mold_plans", to="platform_core.project")),
                ("scope", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mold_plans", to="platform_core.datascope")),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="MoldPlanContext",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("dimension", models.CharField(max_length=32)),
                ("value_code", models.CharField(max_length=128)),
                ("source_type", models.CharField(choices=[("registry", "Registry"), ("cad", "CAD"), ("reference_data", "Reference data"), ("user_confirmed", "User confirmed")], max_length=24)),
                ("source_ref", models.CharField(max_length=255)),
                ("confirmed_by", models.CharField(blank=True, max_length=128)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="context_entries", to="platform_core.moldplan")),
            ],
            options={"ordering": ["dimension"]},
        ),
        migrations.CreateModel(
            name="MoldPlanResolution",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("resolution_number", models.PositiveIntegerField()),
                ("context_checksum", models.CharField(max_length=64)),
                ("ruleset_checksum", models.CharField(max_length=64)),
                ("applicability_checksum", models.CharField(max_length=64)),
                ("selection_mode", models.CharField(max_length=24)),
                ("reason", models.TextField()),
                ("override_reason", models.CharField(blank=True, max_length=512)),
                ("context_snapshot", models.JSONField(default=dict)),
                ("candidate_snapshot", models.JSONField(default=list)),
                ("exclusion_summary", models.JSONField(default=list)),
                ("resolved_by", models.CharField(max_length=128)),
                ("resolved_at", models.DateTimeField(auto_now_add=True)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="resolutions", to="platform_core.moldplan")),
                ("selected_profile", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mold_plan_resolutions", to="platform_core.ruleprofile")),
            ],
            options={"ordering": ["plan", "-resolution_number"]},
        ),
        migrations.CreateModel(
            name="MoldPlanRequirement",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("requirement_type", models.CharField(choices=[("must", "Must"), ("should", "Should"), ("manual_confirmation", "Manual confirmation")], max_length=24)),
                ("evidence_requirement", models.JSONField(default=dict)),
                ("planning_status", models.CharField(choices=[("not_checked", "Not checked"), ("insufficient_data", "Insufficient data"), ("ready_for_review", "Ready for review"), ("manual_confirmation", "Manual confirmation")], max_length=32)),
                ("source_reference_snapshot", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolution", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requirements", to="platform_core.moldplanresolution")),
                ("rule_version", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mold_plan_requirements", to="platform_core.ruleversion")),
            ],
            options={"ordering": ["rule_version__rule_id"]},
        ),
        migrations.AddConstraint(model_name="moldplan", constraint=models.UniqueConstraint(fields=("scope", "plan_code"), name="unique_mold_plan_code")),
        migrations.AddIndex(model_name="moldplan", index=models.Index(fields=["scope", "status", "updated_at"], name="mold_plan_scope_status_idx")),
        migrations.AddIndex(model_name="moldplan", index=models.Index(fields=["mold_revision", "status"], name="mold_plan_revision_idx")),
        migrations.AddConstraint(model_name="moldplancontext", constraint=models.UniqueConstraint(fields=("plan", "dimension"), name="unique_mold_plan_context")),
        migrations.AddConstraint(model_name="moldplanresolution", constraint=models.UniqueConstraint(fields=("plan", "resolution_number"), name="unique_mold_plan_resolution")),
        migrations.AddConstraint(model_name="moldplanrequirement", constraint=models.UniqueConstraint(fields=("resolution", "rule_version"), name="unique_mold_plan_requirement")),
        migrations.RunPython(add_mold_planning_permissions, migrations.RunPython.noop),
    ]
