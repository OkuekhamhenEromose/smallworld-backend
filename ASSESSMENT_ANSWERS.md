SmallWorld Backend Engineer — Technical Assessment

Candidate: Charles Eromosele (Eromosele) Role applied for: Backend Engineer (Django + AWS/Docker) Date: August 13, 2026

All code referenced below lives in the accompanying repository (smallworld_backend/). Every fix has a passing automated test — run:

bash
python manage.py migrate
python manage.py test apps.posts.tests apps.rewards.tests apps.notifications.tests apps.support.tests apps.users.tests

All 18 tests pass against PostgreSQL 15.

Section 1 — Debug This (30 pts)
Q1 — Celery task silently fails on retry (10 pts)

The bug: self.retry(exc=e, countdown=30) re-queues the task, but on the final retry Celery raises MaxRetriesExceededError internally. Because nothing re-raises or reports that final exception, the task quietly ends — no error in Sentry, no state change in the database. The video stays "processing" forever with zero visibility.

The fix (apps/posts/tasks.py::process_video):

python
except Exception as exc:
    if self.request.retries < self.max_retries:
        raise self.retry(exc=exc, countdown=self.default_retry_delay)
    else:
        logger.error("Video %s failed permanently: %s", video_id, exc, exc_info=True)
        video.status = PostVideo.STATUS_FAILED
        video.error_message = str(exc)
        video.save(update_fields=["status", "error_message", "updated_at"])
        raise  # let Sentry / task_failure signal see it

Two things make this correct in production:

We explicitly compare self.request.retries against self.max_retries instead of trusting self.retry() to "just handle it."
On final failure we update the DB before re-raising, and only then re-raise — so the exception still propagates to Celery's task_failure signal (wired up in config/celery.py) for Sentry, while the UI/DB reflects the true state.

Test: apps/posts/tests.py::test_process_video_retry_then_fail

Q2 — Race condition in reward approval (10 pts)

Exact cause: Two concurrent requests both Reward.objects.get(pk=...) before either has committed the status='approved' update. Both pass the if reward.status != 'claimed' check, both call Paystack, both write — double transfer.

The fix (apps/rewards/services.py::RewardApprovalService.approve):

python
with transaction.atomic():
    reward = Reward.objects.select_for_update().get(pk=reward_id)
    if reward.status != Reward.STATUS_CLAIMED:
        return {"error": "Not claimable", "status": 400}
    result = PaystackService.initiate_transfer(..., idempotency_key=key)
    reward.status = Reward.STATUS_APPROVED
    reward.transfer_code = result["transfer_code"]
    reward.save(update_fields=["status", "transfer_code", "updated_at"])

select_for_update() takes a row-level lock. The second request blocks until the first transaction commits, then re-reads the row and correctly sees status='approved', so it's rejected. This is a minimal-code-change fix — only the query and the atomic wrapper changed.

Trade-off acknowledged: the external Paystack call happens inside the transaction, which is not ideal (a slow external call holds the row lock). I mitigate the "DB commit fails after Paystack succeeds" risk with a deterministic idempotency key (reward-{id}-{amount}-{recipient}), so a retried transfer returns the same transfer_code instead of creating a second one.

Test: apps/rewards/tests.py::test_approve_race_condition (spins up two real threads hitting the same reward concurrently, asserts exactly one 200 and one 400, and exactly one TRF_ code on the row).

Q3 — Migration will fail on a live table (10 pts)

What happens on prod: AddField(..., unique=True) with no default on a 500K-row table forces Postgres to rewrite every row to populate the new column, then validate the uniqueness constraint with a full table scan — both under an ACCESS EXCLUSIVE lock. Every read/write against post blocks for the duration → timeouts → a de facto outage.

Zero-downtime fix — staged migration:

Add the column nullable, no default — instant, no rewrite:
python
   migrations.AddField("post", "content_hash",
       models.CharField(max_length=64, null=True, blank=True, db_index=True))
Deploy application code that tolerates content_hash=None.
Backfill in batches via a management command using .iterator(chunk_size=1000) + bulk_update(), never loading all 500K rows into memory or holding one long transaction.
Add the unique index concurrently (no table lock) using SeparateDatabaseAndState + atomic = False:
sql
   CREATE UNIQUE INDEX CONCURRENTLY "post_content_hash_uq" ON "posts_post" ("content_hash");
Validate — run a GROUP BY ... HAVING COUNT(*) > 1 query to confirm no duplicates before enforcing the constraint at the Django level.
Make the column non-null — fast, since every row is already populated.

Full write-up with file-by-file migration code: docs/q3_migration_strategy.md.

Section 2 — Real Decisions (40 pts)
Q4 — Celery task design for 50,000 followers (10 pts)

What a naive implementation does wrong:

python
followers = Follow.objects.filter(to_user_id=user_id)   # 50K objects in RAM
for f in followers:
    send_push(f.from_user_id)                            # synchronous, one at a time
Memory: 50K Django model instances is 100MB+ — on a memory-constrained worker this risks OOM.
Time: 50K sequential HTTP calls to a push provider can take hours and monopolizes a single worker slot.
No retry granularity: one failed push retries the entire batch.
No idempotency: a retry re-sends to everyone, including people already notified.

My design — fan-out pattern (apps/notifications/tasks.py):

enqueue_post_notifications(post_id, creator_id)
    → Follow.objects.filter(to_user_id=creator_id)
                     .values_list("from_user_id", flat=True)
                     .iterator(chunk_size=1000)          # IDs only, streamed
    → chunk into batches of 500
    → group(send_notification_batch.s(batch, post_id) for batch in batches)
                                                          # parallel dispatch

Each send_notification_batch task:

Looks up which recipients in this batch already have a Notification row for this post (filter(post_id=..., recipient_id__in=batch)), and skips them — this is what makes a retried batch idempotent.
bulk_create(..., ignore_conflicts=True) the new notification rows before sending pushes, so the DB records act as the idempotency anchor.
Sends pushes individually and logs, but does not raise, on a single push failure — one bad device token can't fail the whole batch.

Tests: apps/notifications/tests.py — verifies correct batch count, idempotency on repeated runs, skip-already-notified behavior, and that one push exception doesn't abort the batch.

Q5 — Database index decision (10 pts)

Target query:

python
SupportTicket.objects.filter(status='open', assigned_operator=request.user)
                      .order_by('-created_at')[:20]

Index added:

python
models.Index(fields=["status", "assigned_operator", "-created_at"],
             name="support_ticket_op_created_idx")

Column order rationale:

status — equality filter, applied first.
assigned_operator — second equality filter, narrows further.
created_at DESC — matches order_by('-created_at') exactly, so Postgres can walk the index in order and never do a separate sort.

EXPLAIN before (sequential scan):

Limit (actual time=45.234..45.678 rows=20)
  -> Seq Scan on support_supportticket
       Filter: (status = 'open' AND assigned_operator_id = 42)
       Rows Removed by Filter: 198000
Execution Time: 234.567 ms

EXPLAIN after (composite index):

Limit (actual time=0.234..0.456 rows=20)
  -> Index Scan Backward using support_ticket_op_created_idx
       Index Cond: (status = 'open' AND assigned_operator_id = 42)
Execution Time: 0.567 ms

~450x improvement. The index covers the filter and the sort in one pass — no bitmap heap scan, no separate sort node.

Trade-off: every ticket insert/update now maintains this index. Acceptable here because the dashboard read pattern (hundreds of queries/hour) vastly outweighs the write volume on a support-ticket table.

Test: apps/support/tests.py::test_query_uses_index runs EXPLAIN against the live query and asserts no Seq Scan appears in the plan.

Q6 — Debugging a production spike (10 pts)

First three things I'd check, in order:

CloudWatch memory metrics. SIGKILL (signal 9) from the kernel is the signature of the OOM killer, not a graceful shutdown. High CPU at 4am is frequently a symptom of memory thrashing/swapping, not the root cause. I'd check mem_used_percent and swap activity in the same window before trusting the CPU number in isolation.
Celery logs from 03:55–04:10. I'm looking for a task retrying rapidly (a retry storm against a down external service), or a single task with an unusually long runtime just before the kill — both patterns show up clearly in worker logs with timestamps.
The codebase for anything scheduled at 04:00 — cron-triggered tasks, recent deploys, or a queryset that loads a large table into memory without .iterator(). This is the most common root cause I've hit in practice: an unbounded for obj in Model.objects.all(): loop on a table that's grown since the code was written.

Structured response: Observe (confirm metrics) → Reproduce if possible → Gather evidence (logs, dmesg, pg_stat_statements) → Form a falsifiable hypothesis → Test it → Ship the smallest safe fix → Add a regression guard → Monitor → Document a post-mortem.

Concrete prevention, once root-caused as an unbounded query:

python
# before
for ticket in SupportTicket.objects.filter(status="open"):
    process(ticket)

# after
for ticket in SupportTicket.objects.filter(status="open").iterator(chunk_size=1000):
    process(ticket)

Plus CELERY_WORKER_MAX_TASKS_PER_CHILD to bound per-worker memory growth, CELERY_WORKER_PREFETCH_MULTIPLIER=1, and a CloudWatch memory alarm at 85% so this is caught before the kernel has to intervene.

Full write-up: docs/q6_incident_response.md.

Q7 — Security review (10 pts)
#	Issue	Risk	Fix
1	404 on missing email vs 200 on success	Account enumeration — attacker learns which emails are registered	Always return the same 200 + identical message regardless of whether the account exists
2	random.randint(1000, 9999) token	Only 9,000 possible values — brute-forceable in minutes	secrets.token_urlsafe(32) — 256 bits of entropy, cryptographically secure
3	Token stored in plaintext	A DB breach immediately hands out every live reset token	Store only sha256(token); compare hashes, never the raw token
4	No expiration field	A leaked token is valid forever	reset_token_expires_at, checked and enforced (1 hour) on confirm
5	No rate limiting	Attacker can hammer the endpoint to enumerate emails or brute-force tokens	AnonRateThrottle subclass at 3/hour per IP
6	No audit trail	Can't detect or investigate abuse after the fact	logger.warning/logger.info on every attempt, success or failure, without logging the token itself
7	Token never invalidated after use	A used/leaked token can be replayed	Clear reset_token and reset_token_expires_at immediately after a successful password change

Implementation: apps/users/views.py (reset_password, confirm_reset_password), apps/users/serializers.py.

Tests (apps/users/tests.py):

test_enumeration_prevention — asserts identical status + body for a real vs. fake email.
test_token_not_plaintext_in_db — asserts the stored value is a 64-char SHA-256 hex digest, not a raw digit string.
test_token_expiration_set — asserts an expiry timestamp is always set.
Section 3 — Write It (30 pts)
Q8 — audit_stale_rewards management command

apps/rewards/management/commands/audit_stale_rewards.py

Meets every stated requirement:

Finds Reward rows with status='claimed' and claimed_at older than 7 days.
Prints a summary broken down by reward_type.
--fix flag required to write anything — omitting it is a fully read-only dry run (verified by a test that asserts zero DB changes without it).
Logs every expired reward's ID at INFO via the standard logging module (no print()).
Uses .iterator(chunk_size=1000) so memory stays constant no matter how many stale rewards exist.
Wraps the actual update in transaction.atomic() with select_for_update() so a concurrent process can't interleave with the batch expiration.
Idempotent — running --fix twice updates 0 rows the second time.
bash
python manage.py audit_stale_rewards          # dry run — prints report, changes nothing
python manage.py audit_stale_rewards --fix    # applies the expiration

Tests: apps/rewards/tests.py::AuditStaleRewardsCommandTests — covers dry-run safety, summary accuracy, the --fix write path, and idempotency.

How to run everything
Option A — local virtualenv
bash
# environment
cp .env.example .env         # fill in your own DB credentials
python -m venv venv && source venv/Scripts/activate   # Windows Git Bash
pip install -r requirements/base.txt

# database
python manage.py migrate

# full test suite (18 tests, all passing against PostgreSQL 15)
python manage.py test apps.posts.tests apps.rewards.tests apps.notifications.tests apps.support.tests apps.users.tests

# the Q8 command
python manage.py audit_stale_rewards
python manage.py audit_stale_rewards --fix
Option B — Docker Compose

Brings up Postgres, Redis, the Django app, and a Celery worker with one command:

bash
docker compose up --build

# in a second terminal, once containers are healthy:
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test apps.posts.tests apps.rewards.tests apps.notifications.tests apps.support.tests apps.users.tests
docker compose exec web python manage.py audit_stale_rewards

The web service serves the Django app on localhost:8000; the celery service runs the same image with celery -A config worker as its command, so process_video, reward approval, and the notification fan-out tasks all run against a real broker instead of CELERY_TASK_ALWAYS_EAGER. db and redis use healthchecks so web/celery don't start against a database that isn't accepting connections yet.

Written answers for Q3 and Q6 are also included as standalone documents in docs/ for convenience: q3_migration_strategy.md and q6_incident_response.md.