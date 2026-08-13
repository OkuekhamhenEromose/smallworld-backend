"""
Notification model for push notifications and in-app notifications.
"""

import uuid
from django.db import models
from django.conf import settings

# Create your models here.

class Notification(models.Model):
    """
    Records a push notification sent to a user.
    Used for deduplication and inbox-style notification history.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    post = models.ForeignKey(
        "posts.Post",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    post = models.ForeignKey(
        "posts.Post",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["recipient", "created_at"]),
            models.Index(fields=["recipient", "is_read"]),
        ]
    def __str__(self):
        return f"Notification to {self.recipient_id} at {self.created_at}"
