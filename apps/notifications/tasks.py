"""
Celery tasks for large-scale push notifications.
Feature 4: Fan-out pattern for 50K followers.
"""

import logging
from celery import shared_task, group, chord
from django.db import transaction

from apps.users.models import Follow
from apps.posts.models import Post
from .models import Notification

logger = logging.getLogger(__name__)


# Batch size: tune based on push provider rate limits and worker memory.
# 500 followers per batch = 100 tasks for 50K followers.
# Each task is small, fast, and independently retryable.
BATCH_SIZE = 500


def send_push_notification(user_id, message):
    """
    Simulated push notification sender.
    In production: Firebase Cloud Messaging, OneSignal, etc.
    """
    # Simulate API call
    logger.debug("Push sent to user %s: %s", user_id, message[:50])
    return {"user_id": user_id, "status": "delivered"}


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_notification_batch(self, follower_ids, post_id):
    """
    Send notifications to a single batch of followers.
    This task is small, retryable, and memory-safe.

    Idempotency: We create Notification records BEFORE sending pushes.
    If this task retries, the existing records prevent duplicate sends
    (we skip users who already have a notification for this post).
    """
    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        logger.warning("Post %s not found, skipping batch.", post_id)
        return

    message = f"{post.user.username} published a new post!"

    # Deduplication: find followers who already got this notification
    existing_recipient_ids = set(
        Notification.objects.filter(
            post_id=post_id,
            recipient_id__in=follower_ids,
        ).values_list("recipient_id", flat=True)
    )

    new_recipient_ids = [
        uid for uid in follower_ids if uid not in existing_recipient_ids
    ]

    if not new_recipient_ids:
        logger.info("Batch for post %s already processed, skipping.", post_id)
        return

    # Bulk create notification records first (idempotency anchor)
    notification_objects = [
        Notification(
            recipient_id=uid,
            post_id=post_id,
            message=message,
        )
        for uid in new_recipient_ids
    ]

    with transaction.atomic():
        Notification.objects.bulk_create(notification_objects, ignore_conflicts=True)

    # Now send pushes (external side effect)
    # If a push fails, we log but don't fail the whole batch.
    # Individual push failures should not retry the entire batch.
    for uid in new_recipient_ids:
        try:
            send_push_notification(uid, message)
        except Exception as exc:
            logger.warning("Push failed for user %s: %s", uid, exc)
            # Individual push failures are logged but not retried.
            # If push provider is down, we'd use a separate retry queue.

    logger.info(
        "Batch complete for post %s: %d new notifications sent.",
        post_id,
        len(new_recipient_ids),
    )


@shared_task(bind=True, max_retries=3)
def enqueue_post_notifications(self, post_id, creator_id):
    """
    Main entry point: called when a creator publishes a post.
    Fetches follower IDs in a memory-efficient way, chunks them,
    and dispatches batch tasks.

    Memory safety: We use values_list() and iterator() to avoid loading
    50K Follow objects into memory. Only IDs are fetched.
    """
    logger.info("Enqueueing notifications for post %s by creator %s", post_id, creator_id)

    # Memory-efficient: only fetch IDs, use iterator() for streaming
    follower_ids = list(
        Follow.objects.filter(to_user_id=creator_id)
        .values_list("from_user_id", flat=True)
        .iterator(chunk_size=1000)
    )

    total_followers = len(follower_ids)
    if total_followers == 0:
        logger.info("No followers for creator %s, nothing to do.", creator_id)
        return

    # Chunk into batches
    batches = [
        follower_ids[i : i + BATCH_SIZE]
        for i in range(0, total_followers, BATCH_SIZE)
    ]

    logger.info(
        "Dispatching %d batches of max %d for %d followers.",
        len(batches),
        BATCH_SIZE,
        total_followers,
    )

    # Dispatch all batch tasks asynchronously.
    # Using group() allows parallel execution across workers.
    # chord() with a callback is an alternative if we need a "all done" signal.
    from celery import group

    job = group(
        send_notification_batch.s(batch, post_id) for batch in batches
    )
    result = job.apply_async()

    logger.info(
        "Dispatched group %s for post %s.",
        result.id,
        post_id,
    )

    return {
        "post_id": post_id,
        "total_followers": total_followers,
        "batches": len(batches),
        "group_id": result.id,
    }