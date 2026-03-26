# ============================================================
# Agents Service — Dockerfile
# ============================================================
# Uses BuildKit cache mounts for pip (resumable builds).
# OWASP A04: non-root user.
# Lightweight: no torch/sentence-transformers (~200MB image).
# ============================================================

FROM python:3.12-slim

# Metadata
LABEL maintainer="GutsDCEO"
LABEL service="agents"

# Security: don't run as root
RUN groupadd --system appgroup && \
    useradd --system --gid appgroup appuser

# Set working directory
WORKDIR /app

# Install dependencies with BuildKit cache mount.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application code
COPY . .

# Switch to non-root user
USER appuser

# Expose the service port
EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')" || exit 1

# Run the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
