# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Prevent .pyc files and enable unbuffered stdout/stderr (so logs stream immediately)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# psycopg2 needs a C compiler + libpq headers to build against PostgreSQL
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Default command runs the web process; docker-compose overrides this
# for the celery service.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]