"""
Reward model for the SmallWorld assessment.
Tracks cash rewards from 'claimed' through 'approved'/'expired'/'rejected'.
"""

import uuid
from django.db import models
from django.conf import settings


class Reward(models.Model):
    STATUS_CLAIMED = "claimed"
    STATUS_APPROVED = "approved"
    STATUS_EXPIRED = "expired"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_CLAIMED, "Claimed"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_REJECTED, "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rewards",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_CLAIMED,
        db_index=True,
    )
    # Use Decimal for money — never float
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paystack_recipient_code = models.CharField(max_length=100, blank=True)
    # Populated after successful transfer initiation
    transfer_code = models.CharField(max_length=100, blank=True, db_index=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    reward_type = models.CharField(max_length=50, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            # Critical for management command (Feature 8)
            models.Index(fields=["status", "claimed_at"]),
            models.Index(fields=["status", "reward_type"]),
        ]

    def __str__(self):
        return f"Reward({self.id}) {self.status} ${self.amount}"