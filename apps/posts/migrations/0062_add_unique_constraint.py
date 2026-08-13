"""
Migration 0062: Add unique constraint on content_hash using CONCURRENTLY.
This avoids locking the table during index creation.
Requires: PostgreSQL, and the migration must run outside a transaction.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    IMPORTANT: This migration uses RunSQL with CONCURRENTLY.
    In Django, AddConstraint does not support CONCURRENTLY directly.
    We use SeparateDatabaseAndState to:
    - Tell Django about the constraint (state)
    - Run the actual SQL with CONCURRENTLY (database)
    """
    atomic = False  # Required for CONCURRENTLY

    dependencies = [
        ("posts", "0061_backfill_content_hash"),
    ]

    state_operations = [
        migrations.AddConstraint(
            model_name="post",
            constraint=models.UniqueConstraint(
                fields=["content_hash"],
                name="posts_post_content_hash_unique",
            ),
        ),
    ]

    database_operations = [
        migrations.RunSQL(
            sql="""
                CREATE UNIQUE INDEX CONCURRENTLY "posts_post_content_hash_unique"
                ON "posts_post" ("content_hash");
            """,
            reverse_sql="""
                DROP INDEX CONCURRENTLY IF EXISTS "posts_post_content_hash_unique";
            """,
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=database_operations,
            state_operations=state_operations,
        ),
    ]