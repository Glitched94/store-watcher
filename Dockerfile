# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project metadata and source
COPY pyproject.toml README.md ./
COPY src ./src

# Install project (UI extras included)
RUN pip install --upgrade pip \
 && pip install ".[ui]"

# Data volume (SQLite etc.)
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# Default env so UI can read sqlite by default
ENV STATE_DB=/app/data/state.db

EXPOSE 8000

# Default command: UI server
CMD ["uvicorn", "store_watcher.ui:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
