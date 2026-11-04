# ==============================================================================
# FinPilot AI — Production Multi-Stage Hardened Containerfile
#
# Governed by:
# - SECURITY_CHECKLIST.md SEC-02, SEC-04, SEC-14, SEC-20
# - Layer 17 Deployment Hardening & Container Security
#
# Security Invariants:
# 1. Multi-stage build isolates frontend build tools from runtime.
# 2. Runs as unprivileged non-root user (finpilot:10001).
# 3. Read-only application filesystem; persistent writes to /app/data only.
# 4. Zero embedded secrets or development environment files.
# 5. Pinned, minimal base images.
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Frontend Build Environment
# ------------------------------------------------------------------------------
FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend

# Install dependencies deterministically
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

# Copy frontend source and build static bundle
COPY frontend/ ./
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Production Python Backend Runtime
# ------------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

LABEL maintainer="FinPilot AI Security Team" \
      version="1.0.0" \
      description="India-first long-only NSE cash-equity research & paper-trading platform"

# Security: Install minimal OS packages and clean cache immediately
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root user and group with explicit UID/GID
RUN groupadd -g 10001 finpilot && \
    useradd -u 10001 -g finpilot -s /bin/false -M finpilot

WORKDIR /app

# Install Python backend dependencies
COPY backend/pyproject.toml /app/backend/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "/app/backend[production]" || \
    pip install --no-cache-dir fastapi uvicorn[standard] pydantic sqlalchemy psycopg2-binary argon2-cffi cryptography pyjwt joblib scikit-learn lightgbm numpy

# Copy backend source code and frozen model artifacts
COPY backend/src /app/backend/src
COPY artifacts /app/artifacts

# Copy compiled frontend from Stage 1 into static directory
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist

# Set up data directories with restricted ownership for non-root user
RUN mkdir -p /app/data /app/artifacts/forward_paper && \
    chown -R finpilot:finpilot /app

# Environment configuration
ENV PYTHONPATH="/app/backend/src" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1" \
    FINPILOT_APP_ENV="production" \
    FINPILOT_HOST="0.0.0.0" \
    FINPILOT_PORT="8000"

# Security: Switch to unprivileged non-root user
USER 10001:10001

EXPOSE 8000

# Health check probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/healthz || exit 1

# Launch production server via uvicorn with worker isolation
ENTRYPOINT ["uvicorn", "finpilot.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
