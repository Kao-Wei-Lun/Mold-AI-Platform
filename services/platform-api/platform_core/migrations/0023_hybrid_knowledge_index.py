from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("platform_core", "0022_structured_knowledge_chunks")]

    operations = [
        migrations.AddField(
            model_name="knowledgechunk",
            name="embedding_v2_model",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="knowledgechunk",
            name="embedding_v2_dimension",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="knowledgechunk",
            name="embedding_v2_checksum",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="knowledgechunk",
            name="sparse_encoder",
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
