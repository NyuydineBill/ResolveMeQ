from django.db import models

# Create your models here.

class SlackToken(models.Model):
    access_token = models.CharField(max_length=200)
    team_id = models.CharField(max_length=100, blank=True, null=True)
    bot_user_id = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
