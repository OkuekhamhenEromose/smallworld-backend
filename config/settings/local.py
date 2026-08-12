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



# from .base import *

# DEBUG = True

# # SQLite for local dev and tests
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }

# # Run Celery tasks synchronously in tests
# CELERY_TASK_ALWAYS_EAGER = True
# CELERY_TASK_EAGER_PROPAGATES = True

# # Use console email backend
# EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"