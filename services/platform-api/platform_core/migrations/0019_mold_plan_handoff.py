import django.db.models.deletion
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0018_mold_planning"),
    ]

    operations = [
        migrations.CreateModel(
            name="MoldPlanHandoff",
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
                (
                    "handoff_type",
                    models.CharField(
                        choices=[
                            ("design_review", "Design review"),
                            ("cad", "CAD"),
                            ("similarity", "Similarity"),
                            ("cae", "CAE"),
                        ],
                        max_length=24,
                    ),
                ),
                ("target_ref", models.CharField(max_length=255)),
                ("contract_snapshot", models.JSONField(default=dict)),
                ("created_by", models.CharField(max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "resolution",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="handoffs",
                        to="platform_core.moldplanresolution",
                    ),
                ),
                (
                    "review_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="mold_plan_handoffs",
                        to="platform_core.reviewrun",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="moldplanhandoff",
            constraint=models.UniqueConstraint(
                fields=("resolution", "handoff_type"),
                name="unique_mold_plan_handoff",
            ),
        ),
    ]
