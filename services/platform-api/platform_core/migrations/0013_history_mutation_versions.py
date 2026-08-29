import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("platform_core", "0012_caestudy_archive_reason_caestudy_archived_at_and_more")]

    operations = [
        migrations.AddField(
            model_name="artifact",
            name="row_version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="artifact",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="hmiprofileversion",
            name="row_version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="hmiprofileversion",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
