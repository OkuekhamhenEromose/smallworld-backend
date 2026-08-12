"""
User model extensions and Follow relationship.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model with password reset token fields for Feature 7.
    """
    reset_token = models.CharField(max_length=128, blank=True, db_index=True)
    reset_token_expires_at = models.DateTimeField(null=True, blank=True)

    # Override email to enforce uniqueness for password reset security
    email = models.EmailField(unique=True)

    class Meta:
        indexes = [
            models.Index(fields=["reset_token"]),
        ]


class Follow(models.Model):
    """
    Follower relationship: from_user follows to_user.
    Required for Feature 4 (50K follower notifications).
    """
    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="following",
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="followers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("from_user", "to_user")]
        indexes = [
            # Critical: "who follows this user?" for notification fan-out
            models.Index(fields=["to_user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.from_user_id} follows {self.to_user_id}"