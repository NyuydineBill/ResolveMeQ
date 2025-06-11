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

    def sync_to_knowledge_base(self):
        """
        Create or update a KnowledgeBaseArticle from this ticket if it is resolved and has agent_response.
        This method will:
        - Create a new KnowledgeBaseArticle if one does not exist for this ticket's issue_type.
        - Update the article if it already exists, keeping the latest description and agent response.
        - Use the ticket's category and tags for article tagging.
        - This enables automatic enrichment of the knowledge base from real ticket resolutions.
        """
        if self.status == "resolved" and self.agent_response:
            from knowledge_base.models import KnowledgeBaseArticle
            title = f"Resolved: {self.issue_type}"
            content = f"Description: {self.description}\n\nAgent Response: {self.agent_response}"
            tags = [self.category] + (self.tags if self.tags else [])
            # Try to find an existing article for this ticket
            article, created = KnowledgeBaseArticle.objects.get_or_create(
                title=title,
                defaults={
                    "content": content,
                    "tags": tags,
                }
            )
            if not created:
                article.content = content
                article.tags = tags
                article.save()

class TicketInteraction(models.Model):
    """
    Tracks all user and agent interactions related to a ticket for analytics and knowledge base enrichment.
    Types include:
    - clarification: User provides more info or clarification via Slack modal.
    - feedback: User rates the agent's response (helpful/not helpful).
    - agent_response: The AI agent's response to the ticket is logged.
    - user_message: Ticket creation or user-initiated messages.
    This model enables auditing, analytics, and future knowledge extraction from real support conversations.
    """
    INTERACTION_TYPES = [
        ("clarification", "Clarification"),
        ("feedback", "Feedback"),
        ("agent_response", "Agent Response"),
        ("user_message", "User Message"),
    ]
    id = models.AutoField(primary_key=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    interaction_type = models.CharField(max_length=50, choices=INTERACTION_TYPES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.interaction_type} for Ticket {self.ticket.ticket_id} by {self.user.user_id}"
