from django.urls import path
from .views import ticket_analytics

urlpatterns = [
    # Add ticket-related endpoints here
    path("analytics/", ticket_analytics, name="ticket-analytics"),
]
