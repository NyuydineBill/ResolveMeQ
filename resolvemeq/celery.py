import os
from celery import Celery
import ssl

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'resolvemeq.settings')

app = Celery('resolvemeq')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Configure Celery to use Redis as the message broker with SSL
redis_url = "rediss://:bSEDHclfM2KUs4iJGubgw1lt2S8p6mLF7AzCaLnaDRU=@celery-redis-cache.redis.cache.windows.net:6380/0"

app.conf.broker_url = redis_url
app.conf.result_backend = redis_url

# Configure SSL settings
app.conf.broker_use_ssl = {
    'ssl_cert_reqs': None,
    'ssl_ca_certs': None,
    'ssl_certfile': None,
    'ssl_keyfile': None,
}

# Configure task settings
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.accept_content = ['json']
app.conf.task_track_started = True
app.conf.task_time_limit = 30 * 60  # 30 minutes
app.conf.task_soft_time_limit = 25 * 60  # 25 minutes

# Configure retry settings
app.conf.task_default_retry_delay = 60  # 1 minute
app.conf.task_max_retries = 3

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}') 