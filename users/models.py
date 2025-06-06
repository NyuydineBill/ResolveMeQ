from django.db import models

# Create your models here.

class User(models.Model):
    user_id = models.CharField(max_length=50, primary_key=True)  # Changed from AutoField to CharField
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True, blank=True, null=True)
    role = models.CharField(max_length=50, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name
