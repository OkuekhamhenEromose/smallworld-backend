"""
Post and PostVideo models for the SmallWorld assessment.
"""

import uuid
from django.db import models
from django.conf import settings

# Create your models here.
class Post(models.Model):
    """
    User-generated content post.
    content_hash is nullable initially to support staged migration (Feature 3)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='posts',)
    content = models.TextField(blank=False)
    # Staged migration: initially nullable, later made unique after backfill
    content_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"Post {self.id} by {self.user}"

class PostVideo(models.Model):
    """
    Video associated with a Post.
    Processed asynchronously by Celery (Feature 1)
    """
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_DONE, 'Done'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name='video')
    file_path = models.CharField(max_length=255, blank=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"PostVideo {self.id} for Post {self.post.id} - Status: {self.status}"
    