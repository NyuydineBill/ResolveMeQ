from django.db import models
from django.utils import timezone
import uuid

# Create your models here.

class KnowledgeBaseArticle(models.Model):
    kb_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    content = models.TextField()
    tags = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    views = models.IntegerField(default=0)
    helpful_votes = models.IntegerField(default=0)
    total_votes = models.IntegerField(default=0)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']

class LLMResponse(models.Model):
    RESPONSE_TYPES = [
        ('TICKET', 'Ticket Resolution'),
        ('KB', 'Knowledge Base'),
        ('GENERAL', 'General Query')
    ]

    response_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.TextField()
    response = models.TextField()
    response_type = models.CharField(max_length=20, choices=RESPONSE_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    helpful_votes = models.IntegerField(default=0)
    total_votes = models.IntegerField(default=0)
    related_kb_articles = models.ManyToManyField(KnowledgeBaseArticle, blank=True)
    ticket = models.ForeignKey('tickets.Ticket', on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"{self.response_type} - {self.created_at}"

    @property
    def helpfulness_score(self):
        if self.total_votes == 0:
            return 0
        return (self.helpful_votes / self.total_votes) * 100

    class Meta:
        ordering = ['-created_at']
