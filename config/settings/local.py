"""
Local development settings.
"""

from .base import *

DEBUG = True

# Use console email backend for local dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Celery eager mode for local testing (optional — remove if testing real Celery)
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "True").lower() in ("true", "1")

# Debug toolbar (optional)
# INSTALLED_APPS += ["debug_toolbar"]