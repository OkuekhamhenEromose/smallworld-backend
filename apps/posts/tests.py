"""
Tests for Feature 1: Celery Video Processing with Retry Logic and Error Handling.
"""

from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.posts.models import Post, PostVideo
from apps.posts.tasks import process_video, process_video_buggy

User = get_user_model()


class PostVideoTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass",
            email="testuser@example.com",
        )
        self.post = Post.objects.create(user=self.user, content="Test post content")
        self.post_video = PostVideo.objects.create(
            post=self.post,
            file_path="/uploads/video.mp4",
            status=PostVideo.STATUS_PENDING,
        )

    @patch("apps.posts.tasks.run_ffmpeg")
    def test_process_video_success(self, mock_run_ffmpeg):
        """
        Happy path: video processes successfully on first attempt.
        """
        mock_run_ffmpeg.return_value = {
            "output_path": "/uploads/video_processed.mp4"
        }

        result = process_video.run(str(self.post_video.id))

        self.post_video.refresh_from_db()
        self.assertEqual(self.post_video.status, PostVideo.STATUS_DONE)
        self.assertEqual(result["status"], "done")

    @patch("apps.posts.tasks.run_ffmpeg")
    def test_process_video_idempotency(self, mock_run_ffmpeg):
        """
        Re-running on an already-done video should be a no-op.
        """
        self.post_video.status = PostVideo.STATUS_DONE
        self.post_video.save()

        result = process_video.run(str(self.post_video.id))

        mock_run_ffmpeg.assert_not_called()
        self.assertIsNone(result)

    @patch("apps.posts.tasks.run_ffmpeg")
    def test_process_video_retry_then_fail(self, mock_run_ffmpeg):
        """
        Test final retry exhaustion path.
        
        In Celery eager mode, the full retry chain (3 retries with 30s delays)
        does not execute cleanly across multiple attempts. We test the final
        failure behavior by setting max_retries=0, which triggers the
        'final failure' code branch on the first error.
        """
        mock_run_ffmpeg.side_effect = RuntimeError("FFmpeg crash")

        original_max_retries = process_video.max_retries
        process_video.max_retries = 0

        try:
            with self.assertRaises(RuntimeError):
                process_video.run(str(self.post_video.id))
        finally:
            process_video.max_retries = original_max_retries

        self.post_video.refresh_from_db()
        self.assertEqual(self.post_video.status, PostVideo.STATUS_FAILED)
        self.assertIn("FFmpeg crash", self.post_video.error_message)

    @patch("apps.posts.tasks.run_ffmpeg")
    def test_buggy_version_silent_failure(self, mock_run_ffmpeg):
        """
        The buggy version swallows the final failure in some edge cases.
        """
        mock_run_ffmpeg.side_effect = RuntimeError("Persistent failure")

        with self.assertRaises(Exception):
            process_video_buggy.run(str(self.post_video.id))