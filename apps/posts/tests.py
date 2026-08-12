"""
Tests for Feature 1: Celery Video Processing with Retry Logic and Error Handling.
This test suite verifies that the Celery task for processing videos behaves correctly,
"""

from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.posts.models import Post, PostVideo
from apps.posts.tasks import process_video, process_video_buggy

# Create your tests here.

User = get_user_model()

class PostVideoTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass', email='testuser@example.com')
        self.post = Post.objects.create(user=self.user, content='Test post content')
        self.post_video = PostVideo.objects.create(post=self.post, file_path='/uploads/video.mp4', status=PostVideo.STATUS_PENDING)

    @patch('apps.posts.tasks.run_ffmpeg')
    def test_process_video_success(self, mock_run_ffmpeg):
        """Happy path: Video processing succeeds and updates status to DONE."""
        mock_run_ffmpeg.return_value = {"output_path": "/uploads/video_processed.mp4"}

        result = process_video(self.post_video.id)

        self.post_video.refresh_from_db()
        self.assertEqual(self.post_video.status, PostVideo.STATUS_DONE)
        self.assertEqual(result["status"], "done")

    @patch('apps.posts.tasks.run_ffmpeg')
    def test_process_video_idempotency(self, mock_run_ffmpeg):
        """Idempotency: Re-running the task on a DONE video should not change its status."""
        self.post_video.status = PostVideo.STATUS_DONE
        self.post_video.save()

        result = process_video(self.post_video.id)

        # FFmpeg should not be called again since the video is already processed
        mock_run_ffmpeg.assert_not_called()
        self.assertIsNone(result)  # Task should return None for already processed videos

    @patch('apps.posts.tasks.run_ffmpeg')
    def test_process_video_retry_then_fail(self, mock_run_ffmpeg):
        """
        Simulate a task that fails 4 times (initial + 3 retries).
        The final failure should propagate the exception and mark the task as FAILED, which should be reported to Sentry.
        """
        # Simulate transient failures for the first 3 calls, then succeed on the 4th
        mock_run_ffmpeg.side_effect = RuntimeError("FFmpeg crash"),
        # Celery's .run() in eager mode will retry immediately.
        # With max_retries=3, the 4th attempt should raise the exception.
        with self.assertRaises(RuntimeError):
            process_video(self.post_video.id)

        self.post_video.refresh_from_db()
        self.assertEqual(self.post_video.status, PostVideo.STATUS_FAILED)
        self.assertIn("FFmpeg crash", self.post_video.error_message)

    @patch('apps.posts.tasks.run_ffmpeg')
    def test_buggy_version_silent_failure(self, mock_run_ffmpeg):
        """
        Demonstrate the buggy version, the final exception is raised but may not be visible to external reporters because the retry mechanism handles it internally in some edge cases.
        """
        mock_run_ffmpeg.side_effect = RuntimeError("persistence failure")

        # In eager mode, this will raise MaxRetriesExceededError or RuntimeError
        # depending on Celery version. The key issue is observability.
        with self.assertRaises(RuntimeError):
            process_video_buggy(self.post_video.id)
    


