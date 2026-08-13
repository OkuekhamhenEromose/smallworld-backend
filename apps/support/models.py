"""
SupportTicket model for index optimization assessment (Q5).
"""
import uuid
from django.db import models
from django.conf import settings

# Create your models here.
class SupportTicket(models.Model):
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_PENDING = "pending"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
        (STATUS_PENDING, "Pending"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
    )
    assigned_operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
    )
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            # BEFORE: No index (sequential scan)
            # AFTER: Composite index covering filter + sort
            models.Index(
                fields=["status", "assigned_operator", "-created_at"],
                name="support_ticket_op_created_idx",
            ),
        ]

    def __str__(self):
        return f"Ticket({self.id}) {self.status}"
