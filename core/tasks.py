from celery import shared_task
from .celery import app

@app.task
def test_task():
    print("Test task is running!")
    return "Task completed successfully!" 