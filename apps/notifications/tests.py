"""
Tests for Feature 4: large-scale push notifications.
"""

from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.posts.models import Post
from apps.users.models import Follow
from apps.notifications.models import Notification
from apps.notifications.tasks import (
    enqueue_post_notifications,
    send_notification_batch,
    BATCH_SIZE,
)

User = get_user_model()


class NotificationFanOutTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(
            username="creator",
            email="creator@example.com",
            password="testpass",
        )
        self.post = Post.objects.create(user=self.creator, content="Hello World!")

        # FAST: bulk_create users WITHOUT password hashing
        users = [
            User(username=f"follower{i}", email=f"follower{i}@example.com")
            for i in range(150)
        ]
        User.objects.bulk_create(users)

        # FAST: bulk_create follows
        followers = list(User.objects.filter(username__startswith="follower"))
        Follow.objects.bulk_create([
            Follow(from_user=u, to_user=self.creator) for u in followers
        ])
        self.followers = followers

    @patch("apps.notifications.tasks.send_push_notification")
    def test_enqueue_creates_batches(self, mock_push):
        """Verify fan-out creates correct number of batches."""
        result = enqueue_post_notifications.run(str(self.post.id), self.creator.id)
        self.assertEqual(result["total_followers"], 150)
        self.assertEqual(result["batches"], 1)  # 150 / 500 = 1 batch

    @patch("apps.notifications.tasks.send_push_notification")
    def test_batch_idempotency(self, mock_push):
        """Running the same batch twice should not duplicate notifications."""
        batch_ids = [self.followers[0].id, self.followers[1].id]

        send_notification_batch.run(batch_ids, str(self.post.id))
        send_notification_batch.run(batch_ids, str(self.post.id))

        count = Notification.objects.filter(
            post=self.post,
            recipient_id__in=batch_ids,
        ).count()

        self.assertEqual(count, 2)

    @patch("apps.notifications.tasks.send_push_notification")
    def test_batch_skips_already_notified(self, mock_push):
        """If a user already has a notification, they are skipped."""
        batch_ids = [self.followers[0].id]

        send_notification_batch.run(batch_ids, str(self.post.id))
        self.assertEqual(Notification.objects.count(), 1)

        send_notification_batch.run(batch_ids, str(self.post.id))
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(mock_push.call_count, 1)

    @patch("apps.notifications.tasks.send_push_notification")
    def test_individual_push_failure_does_not_fail_batch(self, mock_push):
        """One bad push should not fail the entire batch."""
        mock_push.side_effect = [RuntimeError("Push failed"), None, None]

        batch_ids = [
            self.followers[0].id,
            self.followers[1].id,
            self.followers[2].id,
        ]

        send_notification_batch.run(batch_ids, str(self.post.id))
        self.assertEqual(Notification.objects.count(), 3)