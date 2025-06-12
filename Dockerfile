FROM python:3.11-slim

# Install OpenSSL for TLS support (if needed by your app)
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment
RUN python3 -m venv /app/venv

# Copy requirements.txt into the container
COPY requirements.txt /app/requirements.txt

# Activate the virtual environment and install dependencies
RUN . /app/venv/bin/activate && pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy the rest of the code
COPY . /app

WORKDIR /app

# Set environment variable for Celery
ENV CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP=True

# Start only the Celery worker
CMD ["/app/venv/bin/celery", "-A", "resolvemeq", "worker", "-l", "info"]