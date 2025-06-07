from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Ticket
from .tasks import process_ticket_with_agent

@receiver(post_save, sender=Ticket)
def ticket_created(sender, instance, created, **kwargs):
    """
    Signal handler for when a ticket is created.
    Queues the ticket for processing by the AI agent using Celery.
    """
    if created and not instance.agent_processed:
        # Queue the task with Celery
        process_ticket_with_agent.delay(instance.ticket_id) 