# Celery configuration

import os
from celery import Celery
from celery.signals import task_failure

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')

app = Celery('config')

# Load config from Django settings (CELERY_* keys)
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all registered Django app configs
app.autodiscover_tasks()

@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **kw):
    """
    Global task failure handler to report exceptions to Sentry.
    This ensures that even if a task fails after max retries, the exception is reported.
    """
    import logging
    logger = logging.getLogger("celery.error")
    logger.error(
        "Celery task %s (%s) failed permanently after retries. Exception: %s",
        task_id, sender.name if sender else "unknown", exception, exc_info=True,
    ) 