from django.test import TestCase
from .models import AutomationTask

class AutomationTaskModelTest(TestCase):
    def test_create_task(self):
        task = AutomationTask.objects.create(
            command="restart_server",
            parameters={"server_id": 1},
            status="pending"
        )
        self.assertEqual(task.command, "restart_server")
        self.assertEqual(task.status, "pending")
        self.assertEqual(task.parameters["server_id"], 1)
