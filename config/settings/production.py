"""
Production settings.
"""

from .base import *

DEBUG = False

# Security
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Celery
CELERY_TASK_ALWAYS_EAGER = False

# Logging to file in production
LOGGING["handlers"]["file"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": "/var/log/smallworld/django.log",
    "maxBytes": 10485760,  # 10MB
    "backupCount": 5,
    "formatter": "verbose",
}
LOGGING["loggers"]["django"]["handlers"] = ["file", "console"]
LOGGING["loggers"]["apps"]["handlers"] = ["file", "console"]