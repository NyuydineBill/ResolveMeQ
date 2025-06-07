from django.urls import path
from .views import (
    ticket_analytics,
    process_with_agent,
    task_status,
    ticket_agent_status
)

urlpatterns = [
    # Add ticket-related endpoints here
    path("analytics/", ticket_analytics, name="ticket-analytics"),
    path("<int:ticket_id>/process/", process_with_agent, name="process-with-agent"),
    path("tasks/<str:task_id>/status/", task_status, name="task-status"),
    path("<int:ticket_id>/agent-status/", ticket_agent_status, name="ticket-agent-status"),
]
