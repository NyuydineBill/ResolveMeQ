FROM python:3.11-slim

# Install OpenSSL for TLS support
RUN apk add --no-cache openssl

# Install Python and pip
RUN apk add --no-cache python3 py3-pip

# Create a virtual environment
RUN python3 -m venv /app/venv

# Copy requirements.txt into the container
COPY requirements.txt /app/requirements.txt

# Activate the virtual environment and install dependencies
RUN . /app/venv/bin/activate && pip install -r /app/requirements.txt

# Copy the rest of the code
COPY . /app

WORKDIR /app

# Expose the default Redis port (if needed)
EXPOSE 6379

# Set environment variable for Celery
ENV CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP=True

# Start only the Celery worker
CMD ["/app/venv/bin/celery", "-A", "resolvemeq", "worker", "-l", "info"]