# Dockerfile for ClosedLoop Playground Service & Tier L Local Runner
# Multi-stage / clean Python 3.11 image

FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYGROUND_ENABLED=1

WORKDIR /app

# Install minimal build and runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY playground/requirements-linux.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Create non-root runner user (Section 9: security defense in depth)
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/scratch && \
    chown -R appuser:appuser /app

# Copy application code
COPY --chown=appuser:appuser closedloop /app/closedloop
COPY --chown=appuser:appuser configs /app/configs
COPY --chown=appuser:appuser dashboard /app/dashboard
COPY --chown=appuser:appuser runs /app/runs
COPY --chown=appuser:appuser playground /app/playground

USER appuser

EXPOSE 8000

# Default entrypoint runs the playground server (binds to $PORT or 8000)
CMD ["python", "-m", "playground.server", "--host", "0.0.0.0"]
