from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Ticket
from .tasks import process_ticket_with_agent
from celery.exceptions import OperationalError

@receiver(post_save, sender=Ticket)
def ticket_created(sender, instance, created, **kwargs):
    """
    Signal handler for when a ticket is created.
    Queues the ticket for processing by the AI agent using Celery.
    No retry will be attempted if queuing fails.
    """
    # Skip agent processing during tests if disabled
    if getattr(settings, 'TEST_DISABLE_AGENT', False):
        return
        
    if created and not instance.agent_processed:
        # Queue the task with Celery
        try:
            process_ticket_with_agent.delay(instance.ticket_id)
        except OperationalError as e:
            # Log the error or handle it as needed, but do not retry
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to queue Celery task: {e}")