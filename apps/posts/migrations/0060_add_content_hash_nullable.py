"""
Migration 0060: Add content_hash field to Post model and make it nullable.
This is safe on large tables because adding a nullable column does not require a table rewrite in most databases.
"""

from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('posts', '0059_previous'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='content_hash',
            field=models.CharField(max_length=64, null=True, blank=True, db_index=True),
        ),
    ]