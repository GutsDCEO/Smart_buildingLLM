# ============================================================
# Embedding Service — Dockerfile
# ============================================================
# Uses BuildKit cache mounts for pip (resumable builds).
# OWASP A04: non-root user.
# ============================================================

FROM python:3.12-slim

# Metadata
LABEL maintainer="GutsDCEO"
LABEL service="embedding"

# Security: don't run as root
RUN groupadd --system appgroup && \
    useradd --system --gid appgroup appuser

# Set working directory
WORKDIR /app

# Install dependencies with BuildKit cache mount.
# The pip cache at /root/.cache/pip persists across builds
# inside Docker's Linux layer, making builds resumable if
# they timeout. Each retry picks up where it left off.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application code
COPY . .

# Create a cache directory for the model (owned by appuser)
RUN mkdir -p /app/.cache && chown -R appuser:appgroup /app/.cache
ENV TRANSFORMERS_CACHE=/app/.cache
ENV HF_HOME=/app/.cache

# Switch to non-root user
USER appuser

# Expose the service port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')" || exit 1

# Run the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
