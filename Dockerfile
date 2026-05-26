# Backend image: FastAPI + pipeline + the eval/seed scripts.
FROM python:3.11-slim

WORKDIR /app

# Install Python deps first so this layer caches when only app code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY backend ./backend
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini .
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

# Entrypoint runs migrations, seeds demo data once, then starts the API.
CMD ["./docker-entrypoint.sh"]
