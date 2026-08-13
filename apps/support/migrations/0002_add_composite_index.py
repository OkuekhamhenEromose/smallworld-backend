"""
Add composite index for the admin dashboard query.
This is the answer to Q5.

Column order rationale:
1. status: equality filter (status = 'open')
2. assigned_operator: equality filter (assigned_operator_id = X)
3. created_at DESC: satisfies ORDER BY without separate sort

PostgreSQL can use this index for an Index Scan that covers
both the WHERE clause and the ORDER BY + LIMIT.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("support", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="supportticket",
            index=models.Index(
                fields=["status", "assigned_operator", "-created_at"],
                name="support_ticket_op_created_idx",
            ),
        ),
    ]