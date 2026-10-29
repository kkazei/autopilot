# The hosted backend on Render's free web service (render.yaml points here; the build context is the repo root).
# Only the code the backend runs is copied, by name, so data/, .env, tests and the web app never enter the image:
# Postgres is the source of truth, and secrets arrive as environment variables set in the Render dashboard.
FROM python:3.11-slim

RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-api.txt

COPY --chown=user agents/ agents/
COPY --chown=user backend/ backend/
COPY --chown=user harness/ harness/
COPY --chown=user loops/ loops/
COPY --chown=user mcp_server/ mcp_server/
COPY --chown=user scripts/ scripts/
COPY --chown=user ui/__init__.py ui/controller.py ui/
USER user
ENV PYTHONUNBUFFERED=1 HOME=/home/user PORT=10000

EXPOSE 10000
# Render sets PORT. One worker: the running job and its pending approval live in this process.
CMD ["sh", "-c", "exec uvicorn --factory backend.app:create_app --host 0.0.0.0 --port \"$PORT\" --workers 1"]
