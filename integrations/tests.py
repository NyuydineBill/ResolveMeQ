from django.test import TestCase, Client
import json

class SlackEventsTest(TestCase):
    def test_url_verification(self):
        client = Client()
        payload = {
            "type": "url_verification",
            "challenge": "test_challenge"
        }
        # You may need to mock signature verification for this test
        response = client.post(
            "/api/integrations/slack/events/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_SLACK_REQUEST_TIMESTAMP="1234567890",
            HTTP_X_SLACK_SIGNATURE="v0=fakesignature"
        )
        # This will fail unless you mock verify_slack_request to return True
        self.assertEqual(response.status_code, 403)
