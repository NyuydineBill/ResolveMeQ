from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
import requests
from .models import Ticket
import logging
from core.celery import app
from integrations.views import notify_user_agent_response  # Restored import for Slack feedback
from solutions.models import Solution
from .autonomous_agent import AutonomousAgent, AgentAction

logger = logging.getLogger(__name__)

@app.task(bind=True, max_retries=3)
def process_ticket_with_agent(self, ticket_id, thread_ts=None):
    """
    Celery task to process a ticket with the AI agent.
    Now includes autonomous decision-making and actions.
    """
    logger.info(f"Celery task started for ticket_id={ticket_id}")
    try:
        ticket = Ticket.objects.get(ticket_id=ticket_id)
        
        # Skip if already processed
        if ticket.agent_processed:
            logger.info(f"Ticket {ticket_id} already processed by agent")
            return False

        # Prepare the payload as expected by FastAPI
        payload = {
            "ticket_id": ticket.ticket_id,
            "issue_type": ticket.issue_type,
            "description": ticket.description,
            "category": ticket.category,
            "tags": ticket.tags,
            "user": {
                "id": str(ticket.user.id),
                "name": ticket.user.username,
                "department": getattr(ticket.user, "department", "")
            }
        }

        # Send to agent
        agent_url = getattr(settings, 'AI_AGENT_URL', 'https://agent.resolvemeq.com/api/analyze')
        headers = {"Content-Type": "application/json"}
        logger.info(f"Sending POST to FastAPI: {agent_url} with payload: {payload}")
        response = requests.post(agent_url, json=payload, headers=headers, timeout=30)
        logger.info(f"Received response from FastAPI: {response.status_code} {response.text}")
        response.raise_for_status()

        # Update ticket with agent response
        ticket.agent_response = response.json()
        ticket.agent_processed = True
        ticket.save()

        # --- NEW: Autonomous Agent Decision Making ---
        autonomous_agent = AutonomousAgent(ticket)
        action, params = autonomous_agent.decide_autonomous_action()
        
        logger.info(f"Autonomous agent decided: {action.value} for ticket {ticket_id}")
        
        # Execute the autonomous action
        action_result = execute_autonomous_action.delay(ticket_id, action.value, params)
        
        # --- Create Solution if agent provided steps or resolution ---
        agent_data = ticket.agent_response
        steps = None
        if isinstance(agent_data, dict):
            solution_data = agent_data.get("solution", {})
            steps = solution_data.get("steps") or agent_data.get("resolution_steps") or agent_data.get("steps")
            if steps and isinstance(steps, list):
                steps = "\n".join(steps)
            elif isinstance(steps, str):
                pass  # Already a string
                
        if steps:
            Solution.objects.get_or_create(
                ticket=ticket,
                defaults={
                    "steps": steps,
                    "worked": action == AgentAction.AUTO_RESOLVE,  # Auto-mark as worked if auto-resolved
                    "created_by": ticket.user,
                }
            )

        # --- Sync to knowledge base if ticket is resolved ---
        if ticket.status == "resolved":
            ticket.sync_to_knowledge_base()

        logger.info(f"Successfully processed ticket {ticket_id} with autonomous agent")
        
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

@app.task
def execute_autonomous_action(ticket_id, action, params):
    """
    Execute the autonomous action decided by the agent.
    """
    try:
        ticket = Ticket.objects.get(ticket_id=ticket_id)
        logger.info(f"Executing autonomous action {action} for ticket {ticket_id}")
        
        if action == AgentAction.AUTO_RESOLVE.value:
            return handle_auto_resolve(ticket, params)
        elif action == AgentAction.ESCALATE.value:
            return handle_escalate(ticket, params)
        elif action == AgentAction.REQUEST_CLARIFICATION.value:
            return handle_request_clarification(ticket, params)
        elif action == AgentAction.ASSIGN_TO_TEAM.value:
            return handle_assign_to_team(ticket, params)
        elif action == AgentAction.SCHEDULE_FOLLOWUP.value:
            return handle_schedule_followup(ticket, params)
        elif action == AgentAction.CREATE_KB_ARTICLE.value:
            return handle_create_kb_article(ticket, params)
        else:
            logger.warning(f"Unknown autonomous action: {action}")
            return False
            
    except Exception as e:
        logger.error(f"Error executing autonomous action {action} for ticket {ticket_id}: {str(e)}")
        return False

def handle_auto_resolve(ticket, params):
    """Automatically resolve the ticket."""
    from integrations.views import notify_user_auto_resolution
    
    ticket.status = "resolved"
    ticket.resolution_summary = f"Auto-resolved by AI Agent. {params.get('reasoning', '')}"
    ticket.save()
    
    # Create interaction record
    from tickets.models import TicketInteraction
    TicketInteraction.objects.create(
        ticket=ticket,
        user=ticket.user,
        interaction_type="agent_auto_resolve",
        content=f"Ticket automatically resolved. Steps: {params.get('resolution_steps', [])}"
    )
    
    # Notify user
    notify_user_auto_resolution(str(ticket.user.id), ticket.ticket_id, params)
    
    logger.info(f"Auto-resolved ticket {ticket.ticket_id}")
    return True

def handle_escalate(ticket, params):
    """Escalate the ticket to human support."""
    from integrations.views import notify_escalation
    
    ticket.status = "escalated"
    ticket.priority = params.get("priority", "medium")
    ticket.save()
    
    # Create interaction record
    from tickets.models import TicketInteraction
    TicketInteraction.objects.create(
        ticket=ticket,
        user=ticket.user,
        interaction_type="agent_escalate",
        content=f"Escalated: {params.get('escalation_reason', 'Requires human attention')}"
    )
    
    # Notify user and support team
    notify_escalation(str(ticket.user.id), ticket.ticket_id, params)
    
    logger.info(f"Escalated ticket {ticket.ticket_id}")
    return True

def handle_request_clarification(ticket, params):
    """Request clarification from user."""
    from integrations.views import request_clarification_from_user
    
    ticket.status = "pending_clarification"
    ticket.save()
    
    # Create interaction record
    from tickets.models import TicketInteraction
    TicketInteraction.objects.create(
        ticket=ticket,
        user=ticket.user,
        interaction_type="agent_clarification_request",
        content=f"Requested clarification: {params.get('reason', 'Need more information')}"
    )
    
    # Send clarification request to user
    request_clarification_from_user(str(ticket.user.id), ticket.ticket_id, params)
    
    logger.info(f"Requested clarification for ticket {ticket.ticket_id}")
    return True

def handle_assign_to_team(ticket, params):
    """Assign ticket to specific team."""
    ticket.assigned_team = params.get("assigned_team", "IT Support")
    ticket.priority = params.get("priority", "medium")
    ticket.status = "assigned"
    ticket.save()
    
    logger.info(f"Assigned ticket {ticket.ticket_id} to {ticket.assigned_team}")
    return True

def handle_schedule_followup(ticket, params):
    """Schedule a follow-up check."""
    # Schedule another task to check on this ticket later
    followup_time = params.get("followup_time")
    if followup_time:
        check_ticket_followup.apply_async(
            args=[ticket.ticket_id, params],
            eta=followup_time
        )
    
    # Send solution to user but don't auto-resolve
    from integrations.views import send_solution_with_followup
    send_solution_with_followup(str(ticket.user.id), ticket.ticket_id, params)
    
    logger.info(f"Scheduled follow-up for ticket {ticket.ticket_id}")
    return True

def handle_create_kb_article(ticket, params):
    """Create knowledge base article from resolved ticket."""
    ticket.sync_to_knowledge_base()
    logger.info(f"Created KB article from ticket {ticket.ticket_id}")
    return True

@app.task
def check_ticket_followup(ticket_id, original_params):
    """Follow-up task to check if solution worked."""
    try:
        ticket = Ticket.objects.get(ticket_id=ticket_id)
        
        # If still not resolved, escalate
        if ticket.status not in ["resolved", "closed"]:
            logger.info(f"Follow-up: ticket {ticket_id} not resolved, escalating")
            handle_escalate(ticket, {
                "escalation_reason": "Solution did not resolve issue within expected timeframe",
                "priority": "high"
            })
        else:
            logger.info(f"Follow-up: ticket {ticket_id} successfully resolved")
            
    except Exception as e:
        logger.error(f"Error in follow-up check for ticket {ticket_id}: {str(e)}")