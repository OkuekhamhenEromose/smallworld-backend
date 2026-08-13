"""
Celery tasks for post/video processing.
Feature 1: Video processing with correct retry logic and error handling.
"""

import logging
from celery import shared_task
from django.db import transaction

from .models import PostVideo

logger = logging.getLogger(__name__)

def run_ffmpeg(file_path: str) -> dict:
    """
    Simulate running ffmpeg to process a video file.
    In a real implementation, this would subprocess.call(['ffmpeg', ...]) and handle the output.
    """
    # simulate transient failuer 20% of the time for testing
    import random
    if random.random() < 0.2:
        raise RuntimeError("FFmpeg transient failure: codec not found")

    return {"output_path": file_path.replace(".mp4", "_processed.mp4")}

    
# ============================================================================
# ASSESSMENT BUG VERSION (for demonstration only)
# ============================================================================
# This is the buggy code from Q1. It silently swallows the final failure.
# After max_retries=3, the task stops retrying but the exception is NOT
# propagated to Sentry because retry() internally marks the task as FAILED
# but if no error reporter is hooked into the task failure event, it's silent.
# ============================================================================

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_video_buggy(self, video_id: str):
    """
    Process a video file associated with a PostVideo instance.
    This is the buggy version that does not report final failures to Sentry.
    Demonstrates Q1 asessment bug
    """
    try:
        video = PostVideo.objects.get(id=video_id)
        result = run_ffmpeg(video.file_path)
        video.status = PostVideo.STATUS_DONE
        video.save()
    except PostVideo.DoesNotExist:
        return  # Video not found, nothing to do
    except Exception as e:
        # BUG: On final retry exhaustion, this raises MaxRetriesExceededError
        # but if the caller doesn't handle it, the failure is silent in Sentry.
        # The task state becomes FAILURE but no external error reporter fires.
        self.retry(exc=e, countdown=30)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_video(self, video_id: str):
    """
    Production-safe video processing task.

    Idempotency guarantee: If the video is already processed (status=done),
    this task returns immediately. This prevents double-processing if the
    task is duplicated by the broker or retried after a partial commit.
    """
    try:
        video = PostVideo.objects.get(id=video_id)
    except PostVideo.DoesNotExist:
        logger.warning("Video %s not found, skipping.", video_id)
        return

    # Idempotency check: already processed?
    if video.status == PostVideo.STATUS_DONE:
        logger.info("Video %s already processed, skipping.", video_id)
        return

    # State transition: mark as processing to prevent concurrent work
    # if another worker somehow gets this same task.
    video.status = PostVideo.STATUS_PROCESSING
    video.save(update_fields=["status", "updated_at"])

    try:
        result = run_ffmpeg(video.file_path)
    except Exception as exc:
        # Determine if we should retry or fail permanently.
        retries = self.request.retries
        if retries < self.max_retries:
            logger.warning(
                "Video %s processing failed (attempt %d/%d), retrying in %ds: %s",
                video_id,
                retries + 1,
                self.max_retries + 1,
                self.default_retry_delay,
                exc,
            )
            # Re-raise to trigger Celery's retry mechanism.
            # Celery will catch this and re-queue the task.
            raise self.retry(exc=exc, countdown=self.default_retry_delay)
        else:
            # FINAL RETRY EXHAUSTED.
            # We must NOT swallow this exception. Let it propagate so that:
            # 1. Sentry/error reporter captures it.
            # 2. Celery marks the task as FAILURE with the traceback.
            # 3. We update the DB record to 'failed' so the UI can show status.
            logger.error(
                "Video %s processing failed permanently after %d attempts: %s",
                video_id,
                self.max_retries + 1,
                exc,
                exc_info=True,
            )
            
            video.status = PostVideo.STATUS_FAILED
            video.error_message = str(exc)
            video.save(update_fields=["status", "error_message", "updated_at"])
            # Re-raise the exception so Sentry sees it.
            raise

    # Success path: update to done
    with transaction.atomic():
        video.status = PostVideo.STATUS_DONE
        # In production, we'd store result['output_path'] in a new field
        video.save(update_fields=["status", "updated_at"])

    logger.info("Video %s processed successfully.", video_id)
    return {"video_id": str(video_id), "status": "done"}