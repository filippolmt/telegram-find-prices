# Stage 1: build dependencies
FROM python:3.14-slim AS builder

# uv from official image (no pip install needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Build dependencies for compiling C packages (e.g. aiohttp on Python 3.14)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Precompile bytecode for faster startup; copy mode required for multi-stage
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies only (cacheable layer, unchanged when only source code changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

# Copy source and complete project installation
COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY tests/ tests/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# Stage 2: lightweight final image (no gcc, uv, or build cache)
FROM python:3.14-slim

WORKDIR /app

# Create non-root user and data directory for runtime files (db, sessions)
RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p data \
    && chown -R appuser:appuser /app /home/appuser

# Copy only the built venv and source from builder (no gcc, no build cache)
COPY --from=builder --chown=appuser:appuser /app /app

# Add venv to PATH so python resolves to the venv interpreter
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

CMD ["python", "src/bot.py"]
