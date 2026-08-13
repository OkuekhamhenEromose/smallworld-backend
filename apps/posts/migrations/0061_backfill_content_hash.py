"""
Migration 0061: Backfill content_hash for existing rows.
Uses batching to avoid long-running transactions on large tables. This is safe because the content_hash field is nullable.
"""

import hashlib
from django.db import migrations

def backfill_content_hash(apps, schema_editor):
    """
    Generate a unique content_hash for every existing post.
    In production, you might compute this from the actual content.
    Here we use a deterministic hash based on post ID + content.
    """
    Post = apps.get_model('posts', 'Post')
    db_alias = schema_editor.connection.alias
    # Process in batches to keep memory low and transactions short.
    # PostgreSQL acquires row-level locks, not table locks, during UPDATE.
    batch_size = 1000
    queryset = Post.objects.using(db_alias).filter(content_hash__isnull=True)

    while True:
        # Fetch a batch of posts that need backfilling
        batch = list(queryset[:batch_size])
        if not batch:
            break  # No more posts to process
        for post in batch:
            # Deterministic hash: prevents duplicates if re-run
            post.content_hash = hashlib.sha256(f"{post.id}:{post.content}".encode()).hexdigest()[:64]

        # Bulk update the batch
        Post.objects.using(db_alias).bulk_update(batch, ['content_hash'])

        # progress tracking
        print(f"Backfilled content_hash for {len(batch)} posts...")


class Migration(migrations.Migration):
    dependencies = [
        ('posts', '0060_add_content_hash_nullable'),
    ]

    operations = [
        migrations.RunPython(backfill_content_hash, reverse_code=migrations.RunPython.noop),
    ]
