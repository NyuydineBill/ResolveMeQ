from django.db import models
from users.models import User
import requests
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

# Create your models here.

class Ticket(models.Model):
    CATEGORY_CHOICES = [
        ("wifi", "Wi-Fi"),
        ("laptop", "Laptop"),
        ("vpn", "VPN"),
        ("printer", "Printer"),
        ("email", "Email"),
        ("software", "Software"),
        ("hardware", "Hardware"),
        ("network", "Network"),
        ("account", "Account"),
        ("access", "Access"),
        ("phone", "Phone"),
        ("server", "Server"),
        ("security", "Security"),
        ("cloud", "Cloud"),
        ("storage", "Storage"),
        ("other", "Other"),
    ]
    ticket_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    issue_type = models.CharField(max_length=100)
    status = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)  # <-- Add this line
    screenshot = models.URLField(blank=True, null=True)  # Optional screenshot URL
    assigned_to = models.ForeignKey(
        User,
        related_name="assigned_tickets",
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="other")
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    agent_response = models.JSONField(null=True, blank=True, help_text="Response from the AI agent analyzing this ticket")
    agent_processed = models.BooleanField(default=False, help_text="Whether the AI agent has processed this ticket")

    def __str__(self):
        return f"{self.issue_type} ({self.status})"

    def send_to_agent(self):
        """
        Sends the ticket to the AI agent for processing.
        Returns True if successful, False otherwise.
        """
        if self.agent_processed:
            return False

        try:
            agent_url = getattr(settings, 'AI_AGENT_URL', 'https://agent.resolvemeq.com/analyze/')
            payload = {
                'ticket_id': self.ticket_id,
                'issue_type': self.issue_type,
                'description': self.description,
                'category': self.category,
                'tags': self.tags,
                'user': {
                    'id': self.user.user_id,
                    'name': self.user.name,
                    'department': self.user.department
                }
            }
            
            response = requests.post(agent_url, json=payload)
            response.raise_for_status()
            
            self.agent_response = response.json()
            self.agent_processed = True
            self.save()
            return True
            
        except Exception as e:
            print(f"Error sending ticket {self.ticket_id} to AI agent: {str(e)}")
            return False
