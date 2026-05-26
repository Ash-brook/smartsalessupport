#!/usr/bin/env bash
# Backend container startup: apply migrations, seed + process a demo dataset the first
# time (only if the DB is empty), then launch the API.
set -e

alembic upgrade head

EMAIL_COUNT=$(python -c "from backend.db import SessionLocal; from backend.models import SimulatedEmail; s=SessionLocal(); print(s.query(SimulatedEmail).count()); s.close()" 2>/dev/null || echo 0)
if [ "$EMAIL_COUNT" = "0" ]; then
  echo "Empty database — seeding demo data and running the pipeline once..."
  python scripts/seed.py
  python scripts/run_pipeline.py --once --quiet
fi

exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
