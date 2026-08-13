"""
Migration 0063: Make content_hash non-null.
Safe because all existing rows were backfilled in 0061.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("posts", "0062_add_unique_constraint"),
    ]

    operations = [
        migrations.AlterField(
            model_name="post",
            name="content_hash",
            field=models.CharField(
                max_length=64,
                unique=True,  # Now enforced at Django level too
            ),
        ),
    ]