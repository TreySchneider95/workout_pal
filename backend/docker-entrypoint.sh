#!/bin/sh
set -e

# Apply database migrations, import the seed data on first run, then start the API.
alembic upgrade head
python -m app.cli seed-if-empty
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
