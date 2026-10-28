# The hosted backend on a Hugging Face Space (Docker SDK, free CPU). scripts/deploy_space.py copies this file to the
# root of the Space with only the code the backend needs; data/ is never shipped (Postgres is the source of truth).
# Secrets (OPENROUTER_API_KEY, OPENROUTER_MODELS, BLUESKY_HANDLE, BLUESKY_APP_PASSWORD, DATABASE_URL,
# AUTOPILOT_BACKEND_SECRET) are set in the Space settings and arrive as environment variables at run time.
FROM python:3.11-slim

# Spaces run the container as uid 1000; owning the app directory as that user avoids permission errors.
RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-api.txt

COPY --chown=user . .
USER user
ENV PYTHONUNBUFFERED=1 HOME=/home/user

EXPOSE 7860
# One worker: the running job and its pending approval live in this process.
CMD ["uvicorn", "--factory", "backend.app:create_app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
