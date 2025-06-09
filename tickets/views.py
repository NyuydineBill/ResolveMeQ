from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField
from django.db.models.functions import TruncWeek
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from celery.result import AsyncResult
from celery.exceptions import OperationalError
from .models import Ticket
from .tasks import process_ticket_with_agent
import logging

logger = logging.getLogger(__name__)

# Create your views here.

@api_view(["GET"])
def ticket_analytics(request):
    # Tickets per week (last 8 weeks)
    now = timezone.now()
    weeks_ago = now - timezone.timedelta(weeks=8)
    tickets_per_week = (
        Ticket.objects.filter(created_at__gte=weeks_ago)
        .annotate(week=TruncWeek("created_at"))
        .values("week")
        .annotate(count=Count("ticket_id"))
        .order_by("week")
    )

    # Avg resolution time (tickets with status 'resolved')
    resolved_tickets = Ticket.objects.filter(status="resolved", updated_at__gt=F("created_at"))
    avg_resolution = resolved_tickets.annotate(
        resolution_time=ExpressionWrapper(F("updated_at") - F("created_at"), output_field=DurationField())
    ).aggregate(avg_time=Avg("resolution_time"))["avg_time"]

    # Open vs closed tickets
    open_count = Ticket.objects.exclude(status="resolved").count()
    closed_count = Ticket.objects.filter(status="resolved").count()

    return Response({
        "tickets_per_week": list(tickets_per_week),
        "avg_resolution_time_seconds": avg_resolution.total_seconds() if avg_resolution else None,
        "open_tickets": open_count,
        "closed_tickets": closed_count,
    })

@api_view(['POST'])
def process_with_agent(request, ticket_id):
    """
    Manually trigger AI agent processing for a ticket.
    Uses Celery task for background processing.
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    
    # Reset agent processing status if requested
    if request.data.get('reset', False):
        ticket.agent_processed = False
        ticket.agent_response = None
        ticket.save()
    
    # Queue the task
    try:
        task = process_ticket_with_agent.delay(ticket.ticket_id)
        logger.info(f"Queued Celery task: {task.id} for ticket {ticket.ticket_id}")
        task_id = task.id
        status = 'queued'
    except OperationalError as e:
        logger.error(f"Failed to queue Celery task: {e}")
        task_id = None
        status = 'celery-broker-unavailable'
    
    return Response({
        'task_id': task_id,
        'ticket_id': ticket.ticket_id,
        'status': status,
        'agent_processed': ticket.agent_processed
    })

@api_view(['GET'])
def task_status(request, task_id):
    """
    Check the status of a Celery task.
    """
    task_result = AsyncResult(task_id)
    response = {
        'task_id': task_id,
        'status': task_result.status,
        'successful': task_result.successful(),
        'failed': task_result.failed(),
    }
    
    if task_result.ready():
        if task_result.successful():
            response['result'] = task_result.result
        else:
            response['error'] = str(task_result.result)
    
    return Response(response)

@api_view(['GET'])
def ticket_agent_status(request, ticket_id):
    """
    Get the agent processing status and history for a ticket.
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    
    # Get the latest task for this ticket from Celery
    from celery.task.control import inspect
    i = inspect()
    active_tasks = i.active() or {}
    scheduled_tasks = i.scheduled() or {}
    
    # Find tasks related to this ticket
    ticket_tasks = []
    for worker_tasks in active_tasks.values():
        for task in worker_tasks:
            if task['name'] == 'tickets.tasks.process_ticket_with_agent' and str(ticket_id) in str(task['args']):
                ticket_tasks.append({
                    'task_id': task['id'],
                    'status': 'active',
                    'started_at': task['time_start'],
                })
    
    for worker_tasks in scheduled_tasks.values():
        for task in worker_tasks:
            if task['name'] == 'tickets.tasks.process_ticket_with_agent' and str(ticket_id) in str(task['args']):
                ticket_tasks.append({
                    'task_id': task['id'],
                    'status': 'scheduled',
                    'eta': task['eta'],
                })
    
    return Response({
        'ticket_id': ticket.ticket_id,
        'agent_processed': ticket.agent_processed,
        'agent_response': ticket.agent_response,
        'active_tasks': ticket_tasks,
        'last_updated': ticket.updated_at,
    })
