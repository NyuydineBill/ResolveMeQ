from django.urls import path
from .views import (
    slack_oauth_redirect,
    slack_events,
    slack_slash_command,
    slack_interactive_action,
)

urlpatterns = [
    path("slack/oauth/redirect/", slack_oauth_redirect, name="slack_oauth_redirect"),
    path("slack/events/", slack_events, name="slack_events"),
    path("slack/commands/", slack_slash_command, name="slack_slash_command"),
    path("slack/actions/", slack_interactive_action, name="slack_interactive_action"),
]
