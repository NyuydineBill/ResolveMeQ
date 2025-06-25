from django.test import TestCase
from tickets.models import Ticket
from base.models import User
from .models import Solution

class SolutionModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create(user_id="U123", name="Test User")
        self.ticket = Ticket.objects.create(
            user=self.user,
            issue_type="vpn (medium)",
            status="new",
            description="VPN not connecting",
            category="vpn"
        )

    def test_create_solution(self):
        solution = Solution.objects.create(
            ticket=self.ticket,
            steps="Restart VPN client and try again.",
            worked=True
        )
        self.assertEqual(solution.ticket, self.ticket)
        self.assertTrue(solution.worked)
