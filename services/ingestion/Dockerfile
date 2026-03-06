# ============================================================
# Ingestion Service — Dockerfile
# ============================================================
# Multi-stage not needed yet (simple service).
# Uses non-root user for security (OWASP A04).
# ============================================================

FROM python:3.12-slim

# Metadata
LABEL maintainer="GutsDCEO"
LABEL service="ingestion"

# Security: don't run as root
RUN groupadd --system appgroup && \
    useradd --system --gid appgroup appuser

# Set working directory
WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Switch to non-root user
USER appuser

# Expose the service port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

# Run the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
