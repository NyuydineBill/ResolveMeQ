import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'resolvemeq.settings')

app = Celery('resolvemeq')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Configure Celery to use Redis as the message broker
app.conf.broker_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
app.conf.result_backend = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

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