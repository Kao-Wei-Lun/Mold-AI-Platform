import django.db.models.deletion
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("platform_core", "0020_similaritycomparison")]

    operations = [
        migrations.CreateModel(
            name="CADCrossModalProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tolerance_strictness", models.CharField(choices=[("standard", "Standard"), ("precision", "Precision")], default="standard", max_length=16)),
                ("ctq_count", models.PositiveSmallIntegerField(default=0)),
                ("surface_roughness_ra", models.FloatField(blank=True, null=True)),
                ("flow_length_ratio", models.FloatField(blank=True, null=True)),
                ("projected_area", models.FloatField(blank=True, null=True)),
                ("clamp_force_band", models.CharField(blank=True, max_length=64)),
                ("gate_type", models.CharField(blank=True, max_length=64)),
                ("source_mode", models.CharField(default="manual_demo", max_length=32)),
                ("row_version", models.PositiveIntegerField(default=1)),
                ("updated_by", models.CharField(max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("artifact_version", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="similarity_engineering_profile", to="platform_core.artifactversion")),
            ],
        ),
        migrations.CreateModel(
            name="SimilarityFeedback",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("action", models.CharField(choices=[("accept_reference", "Accept reference"), ("link_mold", "Link mold"), ("load_trial_parameters", "Load trial parameters"), ("not_relevant", "Not relevant")], max_length=32)),
                ("reason_code", models.CharField(blank=True, max_length=64)),
                ("actor_id", models.CharField(max_length=128)),
                ("scope_id", models.CharField(max_length=128)),
                ("idempotency_key", models.CharField(max_length=255, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("candidate_feature_set", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="similarity_feedback", to="platform_core.featureset")),
                ("search", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="feedback", to="platform_core.similaritysearch")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="similarityfeedback",
            index=models.Index(fields=["action", "created_at"], name="similarity_feedback_action_idx"),
        ),
    ]
