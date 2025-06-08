from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
import requests
from .models import Ticket
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def process_ticket_with_agent(self, ticket_id):
    """
    Celery task to process a ticket with the AI agent.
    Includes retry logic and proper error handling.
    """
    logger.info(f"Celery task started for ticket_id={ticket_id}")
    try:
        ticket = Ticket.objects.get(ticket_id=ticket_id)
        
        # Skip if already processed
        if ticket.agent_processed:
            logger.info(f"Ticket {ticket_id} already processed by agent")
            return False

        # Prepare the payload
        payload = {
            'ticket_id': ticket.ticket_id,
            'issue_type': ticket.issue_type,
            'description': ticket.description,
            'category': ticket.category,
            'tags': ticket.tags,
            'user': {
                'id': ticket.user.user_id,
                'name': ticket.user.name,
                'department': ticket.user.department
            }
        }

        # Send to agent
        agent_url = getattr(settings, 'AI_AGENT_URL', 'https://agent.resolvemeq.com/analyze/')
        response = requests.post(agent_url, json=payload, timeout=30)
        response.raise_for_status()

        # Update ticket with agent response
        ticket.agent_response = response.json()
        ticket.agent_processed = True
        ticket.save()

        logger.info(f"Successfully processed ticket {ticket_id} with agent")
        return True

    except requests.RequestException as exc:
        logger.error(f"Error processing ticket {ticket_id} with agent: {str(exc)}")
        try:
            # Retry with exponential backoff
            self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for ticket {ticket_id}")
            return False

    except Ticket.DoesNotExist:
        logger.error(f"Ticket {ticket_id} not found")
        return False

    except Exception as e:
        logger.error(f"Unexpected error processing ticket {ticket_id}: {str(e)}")
        return False

    # Example FastAPI call:
    try:
        response = requests.post("http://your-fastapi-url/endpoint", json={"ticket_id": ticket_id})
        logger.info(f"Sent data to FastAPI for ticket_id={ticket_id}, status={response.status_code}, response={response.text}")
    except Exception as e:
        logger.error(f"Error sending data to FastAPI for ticket_id={ticket_id}: {e}")