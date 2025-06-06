from django.db import models

# Create your models here.

class AutomationTask(models.Model):
    task_id = models.AutoField(primary_key=True)
    command = models.CharField(max_length=100)
    parameters = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=50)
    result = models.TextField(blank=True)
    executed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.command} ({self.status})"
