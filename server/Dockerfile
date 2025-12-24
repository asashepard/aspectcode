# Aspect Code Server
# Production-ready Docker image for Google Cloud Run

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash aspectcode
USER aspectcode

# Copy requirements first for better caching
COPY --chown=aspectcode:aspectcode requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Add local bin to PATH
ENV PATH="/home/aspectcode/.local/bin:${PATH}"

# Copy application code
COPY --chown=aspectcode:aspectcode . .

# Set Python path for module imports
ENV PYTHONPATH=/app

# Cloud Run uses PORT env var (default 8080)
ENV PORT=8080
EXPOSE 8080

# Health check (disabled for Cloud Run - it has its own)
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Run the server - use shell form to allow $PORT substitution
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
