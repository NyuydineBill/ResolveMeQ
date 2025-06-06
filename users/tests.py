from django.test import TestCase
from .models import User

class UserModelTest(TestCase):
    def test_create_user(self):
        user = User.objects.create(user_id="U123", name="Test User", email="test@example.com")
        self.assertEqual(user.user_id, "U123")
        self.assertEqual(user.name, "Test User")
        self.assertEqual(user.email, "test@example.com")
