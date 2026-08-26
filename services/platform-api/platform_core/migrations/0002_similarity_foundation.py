import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("platform_core", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="artifact",
            name="dataset_id",
            field=models.CharField(default="public-demo-v1", max_length=128),
        ),
        migrations.AddField(
            model_name="artifact",
            name="material_code",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="artifact",
            name="product_type",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.CreateModel(
            name="SimilarityProfile",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("profile_key", models.CharField(max_length=128, unique=True)),
                ("schema_version", models.CharField(default="1.0", max_length=32)),
                ("weights", models.JSONField(default=dict)),
                ("candidate_collection", models.CharField(max_length=128)),
                ("index_version", models.CharField(max_length=128)),
                ("status", models.CharField(default="approved_demo", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="FeatureSet",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("feature_type", models.CharField(default="cad_similarity", max_length=64)),
                ("schema_version", models.CharField(default="1.0", max_length=32)),
                (
                    "extractor_name",
                    models.CharField(default="deterministic-cad-features", max_length=128),
                ),
                ("extractor_version", models.CharField(default="1.0.0", max_length=32)),
                ("features", models.JSONField(default=dict)),
                ("vector", models.JSONField(default=list)),
                ("vector_dimension", models.PositiveSmallIntegerField()),
                ("metric", models.CharField(default="cosine", max_length=32)),
                ("normalized", models.BooleanField(default=True)),
                ("vector_checksum", models.CharField(max_length=64)),
                ("index_collection", models.CharField(max_length=128)),
                ("index_version", models.CharField(max_length=128)),
                (
                    "index_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("indexed", "Indexed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=24,
                    ),
                ),
                ("index_error_code", models.CharField(blank=True, max_length=128)),
                ("indexed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "cad_model",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="feature_sets",
                        to="platform_core.cadmodel",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SimilaritySearch",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("top_k", models.PositiveSmallIntegerField(default=10)),
                ("filters", models.JSONField(default=dict)),
                ("result", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "job",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="similarity_search",
                        to="platform_core.job",
                    ),
                ),
                (
                    "profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="searches",
                        to="platform_core.similarityprofile",
                    ),
                ),
                (
                    "query_feature_set",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="query_searches",
                        to="platform_core.featureset",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="featureset",
            constraint=models.UniqueConstraint(
                fields=("cad_model", "feature_type", "schema_version", "extractor_version"),
                name="unique_cad_feature_set_version",
            ),
        ),
        migrations.AddIndex(
            model_name="featureset",
            index=models.Index(
                fields=["index_status", "created_at"], name="feature_index_status_idx"
            ),
        ),
    ]
