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

@csrf_exempt
def slack_slash_command(request):
    """
    Handles incoming Slack slash commands.
    Example: /resetpassword
    """
    if request.method == "POST":
        if not verify_slack_request(request):
            return HttpResponse(status=403)
        command = request.POST.get("command")
        user_id = request.POST.get("user_id")
        channel_id = request.POST.get("channel_id")
        # Example: respond to /resetpassword
        if command == "/resetpassword":
            response = {
                "text": "Do you want to reset your password?",
                "attachments": [
                    {
                        "text": "",
                        "fallback": "You are unable to choose an action",
                        "callback_id": "reset_password",
                        "color": "#3AA3E3",
                        "attachment_type": "default",
                        "actions": [
                            {
                                "name": "reset",
                                "text": "Reset Password",
                                "type": "button",
                                "value": "reset"
                            }
                        ]
                    }
                ]
            }
            return JsonResponse(response)
        return JsonResponse({"text": "Unknown command."})
    return HttpResponse(status=405)

@csrf_exempt
def slack_interactive_action(request):
    """
    Handles interactive actions (e.g., button clicks) from Slack.
    """
    if request.method == "POST":
        if not verify_slack_request(request):
            return HttpResponse(status=403)
        payload = json.loads(request.POST.get("payload", "{}"))
        callback_id = payload.get("callback_id")
        user = payload.get("user", {}).get("id")
        channel = payload.get("channel", {}).get("id")
        actions = payload.get("actions", [])
        # Example: handle reset password button
        if callback_id == "reset_password" and actions and actions[0].get("value") == "reset":
            # Here you would trigger your password reset logic
            response = {
                "text": f"Password reset initiated for <@{user}>. Please check your email.",
                "replace_original": True
            }
            return JsonResponse(response)
        return JsonResponse({"text": "Action not recognized."})
    return HttpResponse(status=405)
