"""
Slack integration views for OAuth, events, slash commands, and interactive actions.
Handles Slack authentication, event verification, ticket creation, notifications, and more.
"""

import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
import json
from django.http import HttpResponse
import hmac
import hashlib
import time
from .models import SlackToken
import requests

def slack_oauth_redirect(request):
    """
    Handles the OAuth redirect from Slack.

    Exchanges the temporary OAuth code provided by Slack for an access token.
    On success, stores the access token securely in the database for future API calls.

    Query Parameters:
        code (str): The temporary OAuth code sent by Slack.

    Returns:
        HttpResponse: "Slack app connected!" on success, or error details on failure.
    """
    code = request.GET.get("code")
    if not code:
        return HttpResponseBadRequest("Missing code parameter.")

    client_id = settings.SLACK_CLIENT_ID
    client_secret = settings.SLACK_CLIENT_SECRET
    redirect_uri = settings.SLACK_REDIRECT_URI

    # Exchange code for access token
    token_url = "https://slack.com/api/oauth.v2.access"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    resp = requests.post(token_url, data=data)
    token_data = resp.json()

    if not token_data.get("ok"):
        return HttpResponse(f"Slack OAuth failed: {token_data.get('error', 'Unknown error')}", status=400)

    # Save access_token and bot_user_id
    SlackToken.objects.create(
        access_token=token_data["access_token"],
        team_id=token_data.get("team", {}).get("id"),
        bot_user_id=token_data.get("bot_user_id"),
    )
    return HttpResponse("Slack app connected!")

def verify_slack_request(request):
    """
    Verifies that incoming requests are genuinely from Slack using the signing secret.

    Checks the request timestamp and signature to prevent replay attacks and ensure authenticity.

    Args:
        request (HttpRequest): The incoming HTTP request from Slack.

    Returns:
        bool: True if the request is verified, False otherwise.
    """
    slack_signing_secret = settings.SLACK_SIGNING_SECRET
    request_body = request.body
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    slack_signature = request.headers.get("X-Slack-Signature")

    # Protect against replay attacks
    if not timestamp or abs(time.time() - int(timestamp)) > 60 * 5:
        return False

    sig_basestring = f"v0:{timestamp}:{request_body.decode('utf-8')}"
    my_signature = "v0=" + hmac.new(
        slack_signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(my_signature, slack_signature or "")

@csrf_exempt
def slack_events(request):
    """
    Handles incoming Slack event subscriptions and interactions.

    Verifies the request signature, responds to Slack's URL verification challenge,
    and processes other event types as needed.

    Methods:
        POST: Processes Slack events and URL verification.

    Returns:
        JsonResponse: For URL verification challenge.
        HttpResponse: 200 OK for other events, 403 Forbidden for failed verification, 400 Bad Request for invalid payloads.
    """
    if request.method == "POST":
        if not verify_slack_request(request):
            return HttpResponse(status=403)
        try:
            payload = json.loads(request.body)
        except Exception:
            return HttpResponse(status=400)
        # Handle Slack URL verification challenge
        if payload.get("type") == "url_verification":
            return JsonResponse({"challenge": payload.get("challenge")})

        event = payload.get("event", {})
        # Respond to app_mention events
        if event.get("type") == "app_mention":
            token_obj = SlackToken.objects.order_by("-created_at").first()
            if token_obj:
                headers = {
                    "Authorization": f"Bearer {token_obj.access_token}",
                    "Content-Type": "application/json",
                }
                reply_data = {
                    "channel": event["channel"],
                    "text": "Hello! You mentioned me :wave:"
                }
                requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=reply_data)
        # Handle message events
        if event.get("type") == "message" and not event.get("bot_id"):
            # Get the latest bot token
            token_obj = SlackToken.objects.order_by("-created_at").first()
            if token_obj:
                headers = {
                    "Authorization": f"Bearer {token_obj.access_token}",
                    "Content-Type": "application/json",
                }
                reply_data = {
                    "channel": event["channel"],
                    "text": "Hello from ResolveMeQ bot! :robot_face:"
                }
                requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=reply_data)
        return HttpResponse(status=200)
    return HttpResponse(status=405)

def notify_user_ticket_created(user_id, ticket_id):
    """
    Sends a Slack DM to the user with the ticket ID after ticket creation.

    Args:
        user_id (str): Slack user ID.
        ticket_id (int): Ticket ID.
    """
    token_obj = SlackToken.objects.order_by("-created_at").first()
    if token_obj:
        headers = {
            "Authorization": f"Bearer {token_obj.access_token}",
            "Content-Type": "application/json",
        }
        reply_data = {
            "channel": user_id,
            "text": (
                f"🎟️ Ticket #{ticket_id} created successfully! We’ll get back to you soon.\n"
                "If you have a screenshot, please upload it here and mention your ticket number."
            ),
        }
        resp = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=reply_data)
        print("Slack ticket created notification:", resp.text)

def notify_user_ticket_resolved(user_id, ticket_id):
    """
    Sends a Slack DM to the user when their ticket is marked as resolved.

    Args:
        user_id (str): Slack user ID.
        ticket_id (int): Ticket ID.
    """
    token_obj = SlackToken.objects.order_by("-created_at").first()
    if token_obj:
        headers = {
            "Authorization": f"Bearer {token_obj.access_token}",
            "Content-Type": "application/json",
        }
        reply_data = {
            "channel": user_id,
            "text": f"🛠️ Your ticket #{ticket_id} is now marked as resolved.",
        }
        resp = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=reply_data)
        print("Slack ticket resolved notification:", resp.text)

@csrf_exempt
def slack_slash_command(request):
    """
    Handles the /resolvemeq slash command.
    - If no argument, opens a modal for ticket creation.
    - If 'status', shows the user's open tickets.

    Methods:
        POST: Processes slash command.

    Returns:
        JsonResponse or HttpResponse
    """
    if request.method == "POST":
        if not verify_slack_request(request):
            return HttpResponse(status=403)
        command = request.POST.get("command")
        text = request.POST.get("text", "").strip().lower()
        trigger_id = request.POST.get("trigger_id")
        user_id = request.POST.get("user_id")

        # Handle /resolvemeq status
        if command == "/resolvemeq" and text == "status":
            from tickets.models import Ticket
            tickets = Ticket.objects.filter(user_id=user_id).order_by("-created_at")
            if tickets.exists():
                status_lines = [
                    f"• Ticket #{t.ticket_id}: {t.issue_type} — {t.status.capitalize()}"
                    for t in tickets
                ]
                status_message = "*Your Tickets:*\n" + "\n".join(status_lines)
            else:
                status_message = "You have no tickets."
            return JsonResponse({"response_type": "ephemeral", "text": status_message})

        # Only handle /resolvemeq (open modal)
        if command == "/resolvemeq" and not text:
            token_obj = SlackToken.objects.order_by("-created_at").first()
            if not token_obj:
                return JsonResponse({"text": "Bot not authorized."})
            # Build modal view
            modal_view = {
                "type": "modal",
                "callback_id": "resolvemeq_modal",
                "title": {"type": "plain_text", "text": "New IT Request"},
                "submit": {"type": "plain_text", "text": "Submit"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "category_block",
                        "element": {
                            "type": "static_select",
                            "action_id": "category",
                            "placeholder": {"type": "plain_text", "text": "Select category"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "Wi-Fi"}, "value": "wifi"},
                                {"text": {"type": "plain_text", "text": "Laptop"}, "value": "laptop"},
                                {"text": {"type": "plain_text", "text": "VPN"}, "value": "vpn"},
                                {"text": {"type": "plain_text", "text": "Printer"}, "value": "printer"},
                                {"text": {"type": "plain_text", "text": "Email"}, "value": "email"},
                                {"text": {"type": "plain_text", "text": "Software"}, "value": "software"},
                                {"text": {"type": "plain_text", "text": "Hardware"}, "value": "hardware"},
                                {"text": {"type": "plain_text", "text": "Network"}, "value": "network"},
                                {"text": {"type": "plain_text", "text": "Account"}, "value": "account"},
                                {"text": {"type": "plain_text", "text": "Access"}, "value": "access"},
                                {"text": {"type": "plain_text", "text": "Phone"}, "value": "phone"},
                                {"text": {"type": "plain_text", "text": "Server"}, "value": "server"},
                                {"text": {"type": "plain_text", "text": "Security"}, "value": "security"},
                                {"text": {"type": "plain_text", "text": "Cloud"}, "value": "cloud"},
                                {"text": {"type": "plain_text", "text": "Storage"}, "value": "storage"},
                                {"text": {"type": "plain_text", "text": "Other"}, "value": "other"},
                            ],
                        },
                        "label": {"type": "plain_text", "text": "Service Category"},
                    },
                    {
                        "type": "input",
                        "block_id": "issue_type_block",
                        "element": {
                            "type": "static_select",
                            "action_id": "issue_type",
                            "placeholder": {"type": "plain_text", "text": "Select issue type"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "Report"}, "value": "report"},
                                {"text": {"type": "plain_text", "text": "Status"}, "value": "status"},
                                {"text": {"type": "plain_text", "text": "Escalate"}, "value": "escalate"},
                            ],
                        },
                        "label": {"type": "plain_text", "text": "Issue Type"},
                    },
                    {
                        "type": "input",
                        "block_id": "urgency_block",
                        "element": {
                            "type": "static_select",
                            "action_id": "urgency",
                            "placeholder": {"type": "plain_text", "text": "Select urgency"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "Low"}, "value": "low"},
                                {"text": {"type": "plain_text", "text": "Medium"}, "value": "medium"},
                                {"text": {"type": "plain_text", "text": "High"}, "value": "high"},
                            ],
                        },
                        "label": {"type": "plain_text", "text": "Urgency"},
                    },
                    {
                        "type": "input",
                        "block_id": "description_block",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "description",
                            "multiline": True,
                        },
                        "label": {"type": "plain_text", "text": "Description"},
                    },
                    {
                        "type": "input",
                        "block_id": "screenshot_block",
                        "optional": True,
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "screenshot",
                            "placeholder": {"type": "plain_text", "text": "Paste screenshot URL (optional)"},
                        },
                        "label": {"type": "plain_text", "text": "Screenshot URL"},
                    },
                ],
            }
            # Open modal
            headers = {
                "Authorization": f"Bearer {token_obj.access_token}",
                "Content-Type": "application/json",
            }
            data = {
                "trigger_id": trigger_id,
                "view": modal_view,
            }
            requests.post("https://slack.com/api/views.open", headers=headers, json=data)
            return HttpResponse()  # Slack expects 200 OK
        return JsonResponse({"text": "Unknown command."})
    return HttpResponse(status=405)

@csrf_exempt
def slack_modal_submission(request):
    """
    Handles modal submissions from Slack and creates a ticket in the backend.

    Methods:
        POST: Processes modal submission.

    Returns:
        JsonResponse: Slack expects a response_action.
    """
    if request.method == "POST":
        if not verify_slack_request(request):
            return HttpResponse(status=403)
        payload = json.loads(request.POST.get("payload", "{}"))
        if payload.get("type") == "view_submission" and payload.get("view", {}).get("callback_id") == "resolvemeq_modal":
            values = payload["view"]["state"]["values"]
            category = values["category_block"]["category"]["selected_option"]["value"]
            issue_type = values["issue_type_block"]["issue_type"]["selected_option"]["value"]
            urgency = values["urgency_block"]["urgency"]["selected_option"]["value"]
            description = values["description_block"]["description"]["value"]
            screenshot = values.get("screenshot_block", {}).get("screenshot", {}).get("value", "")
            user_id = payload["user"]["id"]
            # Save to your Ticket model (example)
            from tickets.models import Ticket
            from users.models import User
            user, _ = User.objects.get_or_create(user_id=user_id, defaults={"name": user_id})
            ticket = Ticket.objects.create(
                user=user,
                issue_type=f"{issue_type} ({urgency})",
                status="new",
                description=description,
                screenshot=screenshot,
                category=category,
            )
            notify_user_ticket_created(user_id, ticket.ticket_id)
            # Respond to Slack (modal closes automatically)
            return JsonResponse({"response_action": "clear"})
        return JsonResponse({}, status=200)
    return HttpResponse(status=405)

@csrf_exempt
def slack_interactive_action(request):
    """
    Handles interactive actions (e.g., button clicks) from Slack.

    Methods:
        POST: Processes interactive actions.

    Returns:
        HttpResponse
    """
    if request.method == "POST":
        if not verify_slack_request(request):
            return HttpResponse(status=403)
        payload = json.loads(request.POST.get("payload", "{}"))
        # Handle different types of interactive actions here
        return HttpResponse(status=200)



    return HttpResponse(status=405)
