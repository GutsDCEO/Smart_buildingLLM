# ============================================================
# Ingestion Service — Dockerfile
# ============================================================
# Uses BuildKit cache mounts for pip (resumable builds).
# OWASP A04: non-root user.
# ============================================================

FROM python:3.12-slim

# Metadata
LABEL maintainer="GutsDCEO"
LABEL service="ingestion"

# Security: don't run as root
RUN groupadd --system appgroup && \
    useradd --system --gid appgroup appuser

# Install OS-level dependencies:
#   tesseract-ocr — OCR engine for scanned PDFs
#   poppler-utils — PDF rendering utilities (pdftoppm)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies with BuildKit cache mount.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

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
