# SmallWorld Backend Engineer — Technical Assessment

This repository contains my completed submission for the SmallWorld
Backend Engineer (Django + AWS/Docker) technical assessment.

📄 **[Read the full written answers → ASSESSMENT_ANSWERS.md](./ASSESSMENT_ANSWERS.md)**

Supporting write-ups:
- [Q3 — Safe migration strategy](./docs/q3_migration_strategy.md)
- [Q6 — EC2 incident response](./docs/q6_incident_response.md)

## Quick start

```bash
cp .env.example .env
python -m venv venv && source venv/Scripts/activate
pip install -r requirements/base.txt
python manage.py migrate
python manage.py test apps.posts.tests apps.rewards.tests apps.notifications.tests apps.support.tests apps.users.tests
```

Or with Docker:

```bash
docker compose up --build
docker compose exec web python manage.py migrate
```