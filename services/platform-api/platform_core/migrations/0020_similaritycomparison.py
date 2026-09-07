import django.db.models.deletion
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("platform_core", "0019_mold_plan_handoff")]

    operations = [
        migrations.CreateModel(
            name="SimilarityComparison",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("roi", models.JSONField(default=dict)),
                ("roi_checksum", models.CharField(max_length=64)),
                (
                    "alignment_status",
                    models.CharField(
                        choices=[("full", "Full"), ("partial", "Partial"), ("skipped", "Skipped")],
                        max_length=16,
                    ),
                ),
                ("transform", models.JSONField(default=list)),
                ("result", models.JSONField(default=dict)),
                ("algorithm_version", models.CharField(default="cpu-registration@1.0", max_length=32)),
                ("created_by", models.CharField(max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "candidate_feature_set",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="similarity_comparisons",
                        to="platform_core.featureset",
                    ),
                ),
                (
                    "search",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="comparisons",
                        to="platform_core.similaritysearch",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="similaritycomparison",
            constraint=models.UniqueConstraint(
                fields=("search", "candidate_feature_set", "roi_checksum", "algorithm_version"),
                name="unique_similarity_comparison_run",
            ),
        ),
    ]
