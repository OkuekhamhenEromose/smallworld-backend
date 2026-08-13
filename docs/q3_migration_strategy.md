Q3 — Safe Migration on a Live 500K-Row Table
The migration in question
python
class Migration(migrations.Migration):
    dependencies = [('post', '0059_previous')]
    operations = [
        migrations.AddField(
            model_name='post',
            name='content_hash',
            field=models.CharField(max_length=64, unique=True),
        )
    ]
What happens if this runs on prod

Adding a CharField(unique=True) with no default to a table with 500,000 existing rows forces PostgreSQL to do two expensive things under an ACCESS EXCLUSIVE lock:

Rewrite every row to populate the new column (Django will demand a default or the migration will fail outright asking for one; even a trivial default still means writing 500K rows).
Scan the whole table to validate the new unique constraint.

ACCESS EXCLUSIVE blocks all reads and writes against post for the duration — on a table this size that's realistically minutes, not seconds. Every request touching posts times out. Health checks fail. The deploy looks like an outage because it is one.

The zero-downtime strategy — six stages
Stage 1 — Add the column, nullable, no default (instant)
python
# 0060_add_content_hash_nullable.py
migrations.AddField(
    model_name="post",
    name="content_hash",
    field=models.CharField(max_length=64, null=True, blank=True, db_index=True),
)

A nullable column with no default is metadata-only in Postgres — no table rewrite, no lock beyond a brief schema-catalog update.

Stage 2 — Deploy application code that tolerates content_hash=None

Ship this before touching any data. The app must work correctly whether or not content_hash is populated yet.

Stage 3 — Backfill in batches
python
def backfill_content_hash(apps, schema_editor):
    Post = apps.get_model("posts", "Post")
    batch_size = 1000
    qs = Post.objects.filter(content_hash__isnull=True)
    while True:
        batch = list(qs[:batch_size])
        if not batch:
            break
        for post in batch:
            post.content_hash = hashlib.sha256(
                f"{post.id}:{post.content}".encode()
            ).hexdigest()
        Post.objects.bulk_update(batch, ["content_hash"])

Batching keeps each transaction short (row-level locks only, released quickly) and memory constant regardless of table size. For very large tables this is better run as a standalone management command outside the deploy window rather than as a data migration, so it can be paused/resumed and monitored independently.

Stage 4 — Add the unique index concurrently (no table lock)

Django's AddConstraint can't use CONCURRENTLY directly, so we split state from database operations:

python
class Migration(migrations.Migration):
    atomic = False  # required for CONCURRENTLY

    dependencies = [("posts", "0061_backfill_content_hash")]

    state_operations = [
        migrations.AddConstraint(
            model_name="post",
            constraint=models.UniqueConstraint(
                fields=["content_hash"], name="posts_post_content_hash_unique"
            ),
        ),
    ]
    database_operations = [
        migrations.RunSQL(
            sql='CREATE UNIQUE INDEX CONCURRENTLY "posts_post_content_hash_unique" ON "posts_post" ("content_hash");',
            reverse_sql='DROP INDEX CONCURRENTLY IF EXISTS "posts_post_content_hash_unique";',
        ),
    ]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=database_operations,
            state_operations=state_operations,
        ),
    ]

CREATE INDEX CONCURRENTLY builds the index without holding a lock that blocks writes — it takes roughly twice as long but the table stays live the whole time.

Stage 5 — Validate before trusting the constraint
sql
SELECT content_hash, COUNT(*)
FROM posts_post
WHERE content_hash IS NOT NULL
GROUP BY content_hash
HAVING COUNT(*) > 1;

Run this and confirm zero rows before proceeding. If duplicates exist, the unique index creation in Stage 4 will simply fail (Postgres won't create an invalid concurrent index silently) — resolve duplicates and retry.

Stage 6 — Make the column non-null
python
migrations.AlterField(
    model_name="post",
    name="content_hash",
    field=models.CharField(max_length=64, unique=True),
)

Fast now, because every row already has a value — Postgres only needs to add the NOT NULL constraint, which is a metadata check against the already-indexed data, not a table rewrite.

Summary
Stage	Operation	Lock impact
1	Add nullable column	Instant, metadata-only
2	Deploy	—
3	Backfill in batches	Short row-level locks only
4	CREATE UNIQUE INDEX CONCURRENTLY	No blocking of reads/writes
5	Validate no duplicates	Read-only
6	NOT NULL	Fast, no rewrite needed

Each stage is independently deployable and reversible, which is the whole point — a single 30-minute outage becomes six boring, low-risk steps.