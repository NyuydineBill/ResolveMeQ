FROM redis:7.2-alpine

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

# Expose the default Redis port
EXPOSE 6379

# Set environment variable for Celery
ENV CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP=True

# Start Redis server with TLS enabled and then start Celery worker
CMD ["sh", "-c", "redis-server --tls-port 6379 --port 0 --tls-cert-file /etc/redis/tls/redis.crt --tls-key-file /etc/redis/tls/redis.key --tls-ca-cert-file /etc/redis/tls/ca.crt & . /app/venv/bin/activate && celery -A resolvemeq worker --loglevel=info"] 