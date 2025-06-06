from django.db import models
from tickets.models import Ticket

class Solution(models.Model):
    solution_id = models.AutoField(primary_key=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)
    steps = models.TextField()
    worked = models.BooleanField(default=False)

    def __str__(self):
        return f"Solution for Ticket {self.ticket_id}"
