from django.db import models

# Create your models here.

class KnowledgeBaseArticle(models.Model):
    kb_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200)
    content = models.TextField()
    tags = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.title
