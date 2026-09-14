# ==============================================================================
# FinGuard: FinTech Verifiable Code Review Engine
# AIM Code Kitchen Season 01 — Track 1: The 24/7 Intelligent Code Reviewer
# Joint Credit: created at Code Kitchen Season 01
# Production Google Cloud Run Dockerfile
# ==============================================================================

FROM python:3.11-slim AS builder

# Avoid generation of .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install OS-level dependencies for PostgreSQL/pgvector client and security tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ==============================================================================
# Production Stage
# ==============================================================================
FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    APP_ENV=production \
    FINTECH_CREDIT="created at Code Kitchen Season 01"

WORKDIR /app

# Install runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create non-root user for enterprise container security (SOC2 compliance)
RUN useradd -m -u 1001 finguard && \
    mkdir -p /app/.finguard && \
    chown -R finguard:finguard /app

# Copy application source code
COPY --chown=finguard:finguard app/ /app/app/
COPY --chown=finguard:finguard migrations/ /app/migrations/
COPY --chown=finguard:finguard pyproject.toml /app/pyproject.toml
COPY --chown=finguard:finguard requirements.txt /app/requirements.txt
COPY --chown=finguard:finguard .finguard/ /app/.finguard/

# Switch to non-root user
USER finguard

# Expose standard Cloud Run port
EXPOSE 8080

# Healthcheck for container orchestration
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/healthz || exit 1

# Start FastAPI server on Cloud Run host port
CMD exec uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-8080} --workers 2
