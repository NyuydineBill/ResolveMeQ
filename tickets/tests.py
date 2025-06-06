from django.test import TestCase
from users.models import User
from .models import Ticket

class TicketModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create(user_id="U123", name="Test User")

    def test_create_ticket(self):
        ticket = Ticket.objects.create(
            user=self.user,
            issue_type="wifi (high)",
            status="new",
            description="Cannot connect to Wi-Fi",
            category="wifi"
        )
        self.assertEqual(ticket.user, self.user)
        self.assertEqual(ticket.issue_type, "wifi (high)")
        self.assertEqual(ticket.status, "new")
        self.assertEqual(ticket.category, "wifi")
