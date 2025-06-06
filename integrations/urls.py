from django.urls import path
from .views import slack_oauth_redirect, slack_events

urlpatterns = [
    path("slack/oauth/redirect/", slack_oauth_redirect, name="slack_oauth_redirect"),
    path("slack/events/", slack_events, name="slack_events"),
]
