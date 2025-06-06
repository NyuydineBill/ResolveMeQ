from django.db import models
from users.models import User

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

    def __str__(self):
        return f"{self.issue_type} ({self.status})"
