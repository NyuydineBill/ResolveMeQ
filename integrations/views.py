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

def slack_oauth_redirect(request):
    """
    Handles the OAuth redirect from Slack.

    Exchanges the temporary OAuth code provided by Slack for an access token.
    On success, stores the access token securely in the database for future API calls.

    Query Parameters:
        code (str): The temporary OAuth code sent by Slack.

    Returns:
        JsonResponse: {"status": "success"} on success, or error details on failure.
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
        return JsonResponse(token_data, status=400)

    # Save token_data["access_token"] securely in DB
    SlackToken.objects.create(
        access_token=token_data["access_token"],
        team_id=token_data.get("team", {}).get("id"),
        bot_user_id=token_data.get("bot_user_id"),
    )
    return JsonResponse({"status": "success"})

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
        # ...handle other event types here...
        return HttpResponse(status=200)
    return HttpResponse(status=405)
