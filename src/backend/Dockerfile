# BuildingAssist backend — built remotely by ACR (no local Docker needed).
FROM python:3.14-slim AS base

# Install uv (fast, reproducible installs from the lockfile).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
  UV_LINK_MODE=copy \
  UV_PYTHON_DOWNLOADS=never \
  PYTHONUNBUFFERED=1 \
  PORT=8000

WORKDIR /app

# Install dependencies first (better layer caching).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy the application code.
COPY app ./app
COPY README.md ./

RUN uv sync --frozen --no-dev

EXPOSE 8000

# Uvicorn honours $PORT so Container Apps ingress can override it.
CMD ["sh", "-c", "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
