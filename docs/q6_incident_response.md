Q6 — EC2 CPU Spike & Celery Worker SIGKILL
The incident
04:00 UTC — CloudWatch alarm: CPU at 91%
04:05 UTC — Celery worker process terminated with SIGKILL (signal 9)
04:06 UTC — Queue backlog begins growing
Why SIGKILL matters

SIGKILL cannot be caught or handled by the process — something external killed it forcibly. The two realistic causes here are the Linux OOM killer (by far the most common cause of an unexplained SIGKILL on a worker process) or a supervisor/systemd resource limit. It is very unlikely to be a manual kill -9 at 4am unless something automated triggered it.

High CPU immediately preceding the kill is consistent with memory thrashing — a process approaching its memory limit can cause heavy swapping, which shows up as CPU load even though the underlying problem is memory, not compute.

First three things I'd check, and why
1. CloudWatch memory metrics (not just CPU)

CPU is the only metric given, but CPU alone doesn't explain a SIGKILL. I'd immediately pull mem_used_percent and swap activity for the same window. If memory was climbing toward 100% right before 04:05, that's strong evidence for OOM. I'd also check dmesg / journalctl -k on the instance for the kernel's own confirmation:

bash
dmesg | grep -i "killed process"

This is checked first because it's the fastest way to either confirm or rule out the single most likely cause.

2. Celery worker logs from 03:55–04:10
bash
journalctl -u celery-worker --since "03:55" --until "04:10"

I'm looking for two patterns specifically:

A retry storm — the same task ID appearing repeatedly in a short window, usually because an external dependency (API, DB) went down and the task has no backoff.
An unusually long-running task with no completion log before the kill — a sign of an unbounded query or an infinite loop that's been accumulating memory the whole time.
3. The codebase — anything scheduled around 04:00, and recent deploys
Cron-triggered tasks scheduled for 04:00 are the prime suspect purely on timing.
I'd grep for querysets that iterate a full table without .iterator() — this is the most common real-world cause of a worker slowly consuming memory until the OOM killer steps in.
I'd check git log for anything deployed in the hours before the incident, since a regression introduced same-day is far more likely than a long-stable code path suddenly failing.
Root cause hypotheses
Hypothesis	Supporting evidence	How to confirm
OOM killer	Memory >90%+ before the kill, dmesg shows "Killed process"	Check CloudWatch memory + dmesg
Runaway/retrying task	Same task ID repeating in logs	Grep Celery logs by task name
Unbounded queryset	Recently deployed code loads a large table without .iterator()	Code review + git blame around the deploy time
Retry storm from a dead dependency	External API/DB shows an outage in the same window	Check the dependency's own status/uptime
Structured response
Observe — confirm CPU, memory, disk, and whether other workers/instances were affected.
Stabilize — restart the worker with reduced concurrency (--concurrency=2) to immediately reduce memory pressure while investigating.
Investigate — correlate the 04:00 timing with cron schedules and deploys; check dmesg for OOM confirmation.
Identify — pin down the specific task/query responsible.
Mitigate — scale the instance up temporarily or add swap if needed to buy time.
Fix — add .iterator(chunk_size=1000) to any unbounded query found; add exponential backoff/circuit breaking if it was a retry storm.
Verify — monitor for at least an hour, confirm the queue drains normally and memory stays flat.
Prevent — add a CloudWatch memory alarm (not just CPU), set CELERY_WORKER_MAX_TASKS_PER_CHILD to recycle workers periodically, and set CELERY_WORKER_PREFETCH_MULTIPLIER=1 so one worker can't hoard a large batch of memory-heavy tasks at once.
Example fix, if the root cause is an unbounded queryset
python
# BEFORE — loads the entire result set into memory
for ticket in SupportTicket.objects.filter(status="open"):
    process(ticket)

# AFTER — streams from the DB in fixed-size chunks
for ticket in SupportTicket.objects.filter(status="open").iterator(chunk_size=1000):
    process(ticket)
Monitoring additions going forward
python
# config/settings/production.py
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000   # recycle workers to bound memory growth
CELERY_WORKER_PREFETCH_MULTIPLIER = 1      # don't let one worker hoard tasks

Plus a CloudWatch alarm on memory (not just CPU) at 85%, so this class of incident is caught and paged on before the kernel has to intervene.

One-paragraph interview answer

First, I'd check CloudWatch memory metrics, because a SIGKILL alongside high CPU strongly suggests the OOM killer rather than a pure compute issue. I'd confirm with dmesg. Second, I'd read the Celery logs for the ten minutes before the incident looking for a retry storm or a long-running task. Third, I'd check the codebase for any 04:00 cron jobs or recent deploys that might have introduced an unbounded query. The fix depends on the root cause — .iterator() and reduced concurrency for OOM, exponential backoff and a circuit breaker for a retry storm — and either way I'd add a CloudWatch memory alarm so this is caught before it kills a worker again.