from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("platform_core", "0021_cross_modal_similarity_feedback")]

    operations = [
        migrations.AddField(
            model_name="knowledgedocument",
            name="pipeline_manifest",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="knowledgechunk",
            name="chunk_level",
            field=models.CharField(default="passage", max_length=24),
        ),
        migrations.AddField(
            model_name="knowledgechunk",
            name="content_type",
            field=models.CharField(default="prose", max_length=24),
        ),
        migrations.AddField(
            model_name="knowledgechunk",
            name="parent_ref",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="knowledgechunk",
            name="citation_anchor",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="knowledgechunk",
            name="parser_metadata",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="knowledgechunk",
            name="tombstoned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="knowledgechunk",
            name="index_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("indexed", "Indexed"),
                    ("failed", "Failed"),
                    ("tombstoned", "Tombstoned"),
                ],
                default="pending",
                max_length=24,
            ),
        ),
    ]
