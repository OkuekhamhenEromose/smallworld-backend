"""
SmallWorld Backend Configuration.
"""

# This ensures Celery loads when Django starts
from .celery import app as celery_app

__all__ = ("celery_app",)