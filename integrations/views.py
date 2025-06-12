"""
Slack integration views for OAuth, events, slash commands, and interactive actions.
Handles Slack authentication, event verification, ticket creation, notifications, and more.
"""

import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
import json
from django.http import HttpResponse
import hmac
import hashlib
import time
from .models import SlackToken
import requests
from django.views import View
from django.utils.decorators import method_decorator

@csrf_exempt
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
            response = JsonResponse({"challenge": payload.get("challenge")})
            response['Content-Type'] = 'application/json; charset=utf-8'
            return response

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
        return HttpResponse(status=200, content_type='text/plain; charset=utf-8')
    return HttpResponse(status=405, content_type='text/plain; charset=utf-8')

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
    Also handles clarification modals for missing info.
    """
    if request.method == "POST":
        if not verify_slack_request(request):
            return HttpResponse(status=403)
        payload = json.loads(request.POST.get("payload", "{}"))
        # Handle clarification modal
        if payload.get("type") == "view_submission" and payload.get("view", {}).get("callback_id") == "clarify_modal":
            values = payload["view"]["state"]["values"]
            description = values["description_block"]["description"]["value"]
            issue_type = values["issue_type_block"]["issue_type"]["value"]
            user_id = payload["user"]["id"]
            from tickets.models import Ticket, TicketInteraction
            ticket = Ticket.objects.filter(user__user_id=user_id, status__in=["new", "in-progress"]).order_by("-created_at").first()
            if ticket:
                ticket.description = description
                ticket.issue_type = issue_type
                ticket.save()
                # Log clarification interaction
                TicketInteraction.objects.create(
                    ticket=ticket,
                    user=ticket.user,
                    interaction_type="clarification",
                    content=f"User clarified: Description='{description}', Issue Type='{issue_type}'"
                )
                # Optionally, reprocess with agent
                from tickets.tasks import process_ticket_with_agent
                process_ticket_with_agent.delay(ticket.ticket_id)
            return JsonResponse({"response_action": "clear"})
        if payload.get("type") == "view_submission" and payload.get("view", {}).get("callback_id") == "resolvemeq_modal":
            values = payload["view"]["state"]["values"]
            category = values["category_block"]["category"]["selected_option"]["value"]
            issue_type = values["issue_type_block"]["issue_type"]["selected_option"]["value"]
            urgency = values["urgency_block"]["urgency"]["selected_option"]["value"]
            description = values["description_block"]["description"]["value"]
            screenshot = values.get("screenshot_block", {}).get("screenshot", {}).get("value", "")
            user_id = payload["user"]["id"]
            from tickets.models import Ticket, TicketInteraction
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
            # Log ticket creation as an interaction
            TicketInteraction.objects.create(
                ticket=ticket,
                user=user,
                interaction_type="user_message",
                content=f"Ticket created: {description}"
            )
            notify_user_ticket_created(user_id, ticket.ticket_id)
            return JsonResponse({"response_action": "clear"})
        if payload.get("type") == "view_submission" and payload.get("view", {}).get("callback_id") == "feedback_text_modal":
            ticket_id = payload["view"].get("private_metadata")
            feedback = payload["view"]["state"]["values"]["feedback_block"]["feedback_text"]["value"]
            user_id = payload["user"]["id"]
            from tickets.models import Ticket, TicketInteraction
            try:
                ticket = Ticket.objects.get(ticket_id=ticket_id)
                TicketInteraction.objects.create(
                    ticket=ticket,
                    user=ticket.user,
                    interaction_type="feedback",
                    content=f"User feedback: {feedback}"
                )
            except Exception:
                pass
            return JsonResponse({"response_action": "clear"})
        return JsonResponse({}, status=200)
    return HttpResponse(status=405)

@method_decorator(csrf_exempt, name="dispatch")
class SlackInteractiveActionView(View):
    """
    Handles Slack interactive message actions (button clicks, etc.) sent via POST from Slack.
    Exempts this endpoint from CSRF protection, as Slack does not send CSRF tokens.
    Verifies Slack request signature for security.
    """
    def dispatch(self, request, *args, **kwargs):
        from django.http import HttpResponseNotAllowed
        print("Method received:", request.method)
        if request.method.lower() != 'post':
            return HttpResponseNotAllowed(['POST'])
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        print("IN POST METHOD")
        if not verify_slack_request(request):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Slack interactive POST forbidden: signature verification failed. Headers: %s, Body: %s", dict(request.headers), request.body)
            return HttpResponse(status=403)
        payload = json.loads(request.POST.get("payload", "{}"))
        actions = payload.get("actions", [])
        user_id = payload.get("user", {}).get("id")
        response_url = payload.get("response_url")
        thread_ts = payload.get("message", {}).get("ts")  # Get thread timestamp if present
        # Only handle button actions
        if actions:
            action = actions[0]
            action_id = action.get("action_id")
            value = action.get("value", "")
            # Handle "Ask Again"
            if action_id == "ask_again" and value.startswith("ask_again_"):
                ticket_id = value.replace("ask_again_", "")
                from tickets.tasks import process_ticket_with_agent
                # Post progress update in thread
                token_obj = SlackToken.objects.order_by("-created_at").first()
                if token_obj:
                    headers = {
                        "Authorization": f"Bearer {token_obj.access_token}",
                        "Content-Type": "application/json",
                    }
                    progress_msg = {
                        "channel": user_id,
                        "text": f"🔄 Working on Ticket #{ticket_id}...",
                        "thread_ts": thread_ts or None
                    }
                    resp = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=progress_msg)
                    if resp.ok:
                        progress_data = resp.json()
                        thread_ts = progress_data.get("ts", thread_ts)
                # Pass thread_ts to Celery task
                process_ticket_with_agent.delay(ticket_id, thread_ts)
                requests.post(response_url, json={
                    "replace_original": False,
                    "text": f"🔄 Ticket #{ticket_id} is being reprocessed by the agent."
                })
                return HttpResponse()
            # Handle "Mark as Resolved"
            elif action_id == "resolve_ticket" and value.startswith("resolve_"):
                ticket_id = value.replace("resolve_", "")
                from tickets.models import Ticket
                try:
                    ticket = Ticket.objects.get(ticket_id=ticket_id)
                    ticket.status = "resolved"
                    ticket.save()
                    notify_user_ticket_resolved(user_id, ticket_id)
                    # Prompt for feedback
                    token_obj = SlackToken.objects.order_by("-created_at").first()
                    if token_obj:
                        headers = {
                            "Authorization": f"Bearer {token_obj.access_token}",
                            "Content-Type": "application/json",
                        }
                        feedback_blocks = [
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": f"How helpful was the agent's response for Ticket #{ticket_id}?"}
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "👍 Helpful"},
                                    "value": f"feedback_positive_{ticket_id}",
                                    "action_id": "feedback_positive"
                                },
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": "👎 Not Helpful"},
                                    "value": f"feedback_negative_{ticket_id}",
                                    "action_id": "feedback_negative"
                                }
                            ]
                        }
                    ]
                        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json={
                            "channel": user_id,
                            "blocks": feedback_blocks,
                            "text": "Please rate the agent's response."
                        })
                    requests.post(response_url, json={
                        "replace_original": False,
                        "text": f"✅ Ticket #{ticket_id} marked as resolved."
                    })
                except Ticket.DoesNotExist:
                    requests.post(response_url, json={
                        "replace_original": False,
                        "text": f"❌ Ticket #{ticket_id} not found."
                    })
                return HttpResponse()
            # Handle feedback buttons
            elif action_id in ("feedback_positive", "feedback_negative"):
                feedback = "helpful" if action_id == "feedback_positive" else "not helpful"
                ticket_id = value.split("_")[-1]
                # Log feedback as TicketInteraction
                from tickets.models import Ticket, TicketInteraction
                try:
                    ticket = Ticket.objects.get(ticket_id=ticket_id)
                    TicketInteraction.objects.create(
                        ticket=ticket,
                        user=ticket.user,
                        interaction_type="feedback",
                        content=f"User marked agent response as: {feedback}"
                    )
                    # Sync to knowledge base if resolved and has agent response
                    ticket.sync_to_knowledge_base()
                except Exception:
                    pass
                requests.post(response_url, json={
                    "replace_original": False,
                    "text": f"Thank you for your feedback on Ticket #{ticket_id}: *{feedback}*."
                })
                return HttpResponse()
            # Handle clarification prompt
            elif action_id == "clarify_ticket" and value.startswith("clarify_"):
                ticket_id = value.replace("clarify_", "")
                # Open a modal for the user to provide more info
                token_obj = SlackToken.objects.order_by("-created_at").first()
                if token_obj:
                    headers = {
                        "Authorization": f"Bearer {token_obj.access_token}",
                        "Content-Type": "application/json",
                    }
                    modal_view = {
                        "type": "modal",
                        "callback_id": "clarify_modal",
                        "title": {"type": "plain_text", "text": "Provide More Info"},
                        "submit": {"type": "plain_text", "text": "Submit"},
                        "close": {"type": "plain_text", "text": "Cancel"},
                        "blocks": [
                            {
                                "type": "input",
                                "block_id": "description_block",
                                "element": {
                                    "type": "plain_text_input",
                                    "action_id": "description",
                                    "multiline": True,
                                },
                                "label": {"type": "plain_text", "text": "Description (required)"},
                            },
                            {
                                "type": "input",
                                "block_id": "issue_type_block",
                                "element": {
                                    "type": "plain_text_input",
                                    "action_id": "issue_type",
                                },
                                "label": {"type": "plain_text", "text": "Issue Type (required)"},
                            },
                        ],
                    }
                    trigger_id = payload.get("trigger_id")
                    data = {
                        "trigger_id": trigger_id,
                        "view": modal_view,
                    }
                    requests.post("https://slack.com/api/views.open", headers=headers, json=data)
                return HttpResponse()
            elif action_id == "cancel_ticket" and value.startswith("cancel_"):
                ticket_id = value.replace("cancel_", "")
                requests.post(response_url, json={
                    "replace_original": False,
                    "text": f"❌ Ticket #{ticket_id} update cancelled."
                })
                return HttpResponse()
            # Handle "Escalate" action
            elif action_id == "escalate_ticket" and value.startswith("escalate_"):
                ticket_id = value.replace("escalate_", "")
                from tickets.models import Ticket, TicketInteraction
                try:
                    ticket = Ticket.objects.get(ticket_id=ticket_id)
                    TicketInteraction.objects.create(
                        ticket=ticket,
                        user=ticket.user,
                        interaction_type="user_message",
                        content="User requested escalation via Slack."
                    )
                    # Optionally, notify admins or escalation channel here
                except Exception:
                    pass
                requests.post(response_url, json={
                    "replace_original": False,
                    "text": f"🚨 Ticket #{ticket_id} has been escalated. An IT admin will review it shortly."
                })
                return HttpResponse()
            # Handle feedback text button
            elif action_id == "feedback_text" and value.startswith("feedback_"):
                ticket_id = value.replace("feedback_", "")
                token_obj = SlackToken.objects.order_by("-created_at").first()
                if token_obj:
                    headers = {
                        "Authorization": f"Bearer {token_obj.access_token}",
                        "Content-Type": "application/json",
                    }
                    modal_view = {
                        "type": "modal",
                        "callback_id": "feedback_text_modal",
                        "title": {"type": "plain_text", "text": "Provide Feedback"},
                        "submit": {"type": "plain_text", "text": "Send"},
                        "close": {"type": "plain_text", "text": "Cancel"},
                        "private_metadata": ticket_id,
                        "blocks": [
                            {
                                "type": "input",
                                "block_id": "feedback_block",
                                "element": {
                                    "type": "plain_text_input",
                                    "action_id": "feedback_text",
                                    "multiline": True,
                                    "placeholder": {"type": "plain_text", "text": "Type your feedback or describe your issue..."}
                                },
                                "label": {"type": "plain_text", "text": "Your Feedback"},
                            }
                        ]
                    }
                    trigger_id = payload.get("trigger_id")
                    data = {
                        "trigger_id": trigger_id,
                        "view": modal_view,
                    }
                    requests.post("https://slack.com/api/views.open", headers=headers, json=data)
                return HttpResponse()
        # Always return a 200 OK if no actions matched
        return HttpResponse("No action taken", status=200)

def notify_user_agent_response(user_id, ticket_id, agent_response, thread_ts=None):
    """
    Sends a Slack DM to the user with the agent's response and interactive buttons.
    Formats the agent response for readability and prioritizes a main answer if present.
    """
    token_obj = SlackToken.objects.order_by("-created_at").first()
    if token_obj:
        headers = {
            "Authorization": f"Bearer {token_obj.access_token}",
            "Content-Type": "application/json",
        }
        # Log agent response as TicketInteraction
        from tickets.models import Ticket, TicketInteraction
        try:
            ticket = Ticket.objects.get(ticket_id=ticket_id)
            # Log agent response as TicketInteraction
            TicketInteraction.objects.create(
                ticket=ticket,
                user=ticket.user,  # or a system/bot user if you have one
                interaction_type="agent_response",
                content=str(agent_response)
            )
        except Exception:
            pass
    # Format agent response for Slack
    if isinstance(agent_response, dict) and agent_response.get("error"):
        response_text = f":warning: Sorry, the agent could not process your ticket. Reason: {agent_response['error']}"
    elif isinstance(agent_response, dict):
        # 1. Try to extract a main answer field
        main_answer = (
            agent_response.get("answer") or
            agent_response.get("response") or
            agent_response.get("summary") or
            None
        )
        # 2. Build a readable summary from agent_response
        analysis = agent_response.get("analysis", {})
        recommendations = agent_response.get("recommendations", {})
        assignment = agent_response.get("assignment", {})

        summary_lines = []
        if main_answer:
            summary_lines.append(f"*Answer:*\n{main_answer}")
        if analysis:
            if analysis.get("suggested_category"):
                summary_lines.append(f"*Suggested Category:* {analysis['suggested_category']}")
            if analysis.get("suggested_tags"):
                summary_lines.append(f"*Suggested Tags:* {', '.join(analysis['suggested_tags'])}")
            if analysis.get("similar_tickets"):
                summary_lines.append(f"*Similar Tickets:* {', '.join(map(str, analysis['similar_tickets']))}")
        if recommendations:
            if recommendations.get("immediate_actions"):
                summary_lines.append("*Immediate Actions:*\n" + "\n".join(f"• {a}" for a in recommendations["immediate_actions"]))
            if recommendations.get("resolution_steps"):
                summary_lines.append("*Resolution Steps:*\n" + "\n".join(f"• {a}" for a in recommendations["resolution_steps"]))
            if recommendations.get("preventive_measures"):
                summary_lines.append("*Preventive Measures:*\n" + "\n".join(f"• {a}" for a in recommendations["preventive_measures"]))
        if assignment:
            if assignment.get("suggested_assignee"):
                summary_lines.append(f"*Suggested Assignee:* <@{assignment['suggested_assignee']}> ({assignment.get('team', '')})")
            if assignment.get("reason"):
                summary_lines.append(f"_Reason:_ {assignment['reason']}")

        response_text = "\n".join(summary_lines) if summary_lines else "The agent has processed your ticket. No additional details."
    else:
        response_text = str(agent_response)

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🤖 Response for Ticket #{ticket_id}:*\n{response_text}"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Ask Again"},
                    "value": f"ask_again_{ticket_id}",
                    "action_id": "ask_again"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Provide More Info"},
                    "value": f"clarify_{ticket_id}",
                    "action_id": "clarify_ticket"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Escalate"},
                    "style": "danger",
                    "value": f"escalate_{ticket_id}",
                    "action_id": "escalate_ticket"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Cancel"},
                    "value": f"cancel_{ticket_id}",
                    "action_id": "cancel_ticket"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Mark as Resolved"},
                    "style": "primary",
                    "value": f"resolve_{ticket_id}",
                    "action_id": "resolve_ticket"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Provide Feedback"},
                    "value": f"feedback_{ticket_id}",
                    "action_id": "feedback_text"
                },
            ]
        }
    ]
    reply_data = {
        "channel": user_id,
        "text": response_text,
        "blocks": blocks
    }
    if thread_ts:
        reply_data["thread_ts"] = thread_ts
    resp = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=reply_data)
    print("Slack agent response notification:", resp.text)
