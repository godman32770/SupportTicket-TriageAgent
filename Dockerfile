# Minimal Dockerfile for Support Triage Agent
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable stdout/stderr unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install OS deps needed for building wheels if any
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

# Upgrade pip and install package in editable mode; include pytest for convenience
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -e . \
    && python -m pip install --no-cache-dir pytest

# Default entrypoint runs the CLI module. Provide default to show help; override in docker run.
ENTRYPOINT ["python", "-m", "app.cli.main"]
CMD ["--help"]
