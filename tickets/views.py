from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField
from django.db.models.functions import TruncWeek
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from celery.result import AsyncResult
from celery.exceptions import OperationalError
from .models import Ticket, TicketInteraction
from .tasks import process_ticket_with_agent
from .serializers import TicketSerializer, TicketInteractionSerializer
import logging
from django.conf import settings
from users.models import User
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

# Create your views here.

@api_view(["GET"])
def ticket_analytics(request):
    """
    Get ticket analytics data: tickets per week, average resolution time, open/closed ticket count.
    """
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

@api_view(["POST"])
def create_ticket(request):
    """
    Create a new ticket (web portal).
    """
    serializer = TicketSerializer(data=request.data)
    if serializer.is_valid():
        user_id = request.data.get("user")
        user = User.objects.get(user_id=user_id)
        ticket = serializer.save(user=user, status="new")
        TicketInteraction.objects.create(
            ticket=ticket,
            user=user,
            interaction_type="user_message",
            content=f"Ticket created: {ticket.description}"
        )
        # Optionally trigger agent processing
        from .tasks import process_ticket_with_agent
        process_ticket_with_agent.delay(ticket.ticket_id)
        return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["POST"])
def clarify_ticket(request, ticket_id):
    """
    Add clarification to a ticket (web portal).
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    description = request.data.get("description")
    issue_type = request.data.get("issue_type")
    if not description or not issue_type:
        return Response({"error": "Description and issue_type are required."}, status=400)
    ticket.description = description
    ticket.issue_type = issue_type
    ticket.save()
    TicketInteraction.objects.create(
        ticket=ticket,
        user=ticket.user,
        interaction_type="clarification",
        content=f"User clarified: Description='{description}', Issue Type='{issue_type}'"
    )
    from .tasks import process_ticket_with_agent
    process_ticket_with_agent.delay(ticket.ticket_id)
    return Response(TicketSerializer(ticket).data)

@api_view(["POST"])
def feedback_ticket(request, ticket_id):
    """
    Add feedback to a ticket (web portal).
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    feedback = request.data.get("feedback")
    if not feedback:
        return Response({"error": "Feedback is required."}, status=400)
    TicketInteraction.objects.create(
        ticket=ticket,
        user=ticket.user,
        interaction_type="feedback",
        content=f"User feedback: {feedback}"
    )
    return Response({"message": "Feedback received."})

@api_view(["GET"])
def ticket_history(request, ticket_id):
    """
    Get ticket history (recent interactions).
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    interactions = TicketInteraction.objects.filter(ticket=ticket).order_by("-created_at")[:10]
    serializer = TicketInteractionSerializer(interactions, many=True)
    return Response(serializer.data)

@api_view(["GET"])
def list_tickets(request):
    """
    List all tickets. Optionally filter by user (user_id query param) or status.
    Example: /api/tickets/?user_id=U123&status=new
    """
    user_id = request.GET.get("user_id")
    status_param = request.GET.get("status")
    queryset = Ticket.objects.all().order_by("-created_at")
    if user_id:
        queryset = queryset.filter(user__user_id=user_id)
    if status_param:
        queryset = queryset.filter(status=status_param)
    serializer = TicketSerializer(queryset, many=True)
    return Response(serializer.data)

@api_view(["GET"])
def get_ticket(request, ticket_id):
    """
    Retrieve details for a single ticket by ticket_id.
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    serializer = TicketSerializer(ticket)
    return Response(serializer.data)

@api_view(["PATCH"])
def update_ticket(request, ticket_id):
    """
    Update ticket status or details. Accepts partial updates (e.g., status, description).
    Example body: {"status": "resolved"}
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    serializer = TicketSerializer(ticket, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["GET"])
def search_tickets(request):
    """
    Search and filter tickets by keyword, status, category, date, etc.
    Query params: q (keyword), status, category, created_after, created_before
    """
    queryset = Ticket.objects.all()
    q = request.GET.get("q")
    if q:
        queryset = queryset.filter(description__icontains=q)
    status_param = request.GET.get("status")
    if status_param:
        queryset = queryset.filter(status=status_param)
    category = request.GET.get("category")
    if category:
        queryset = queryset.filter(category=category)
    created_after = request.GET.get("created_after")
    if created_after:
        queryset = queryset.filter(created_at__gte=created_after)
    created_before = request.GET.get("created_before")
    if created_before:
        queryset = queryset.filter(created_at__lte=created_before)
    serializer = TicketSerializer(queryset.order_by("-created_at"), many=True)
    return Response(serializer.data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_attachment(request, ticket_id):
    """
    Upload an attachment (file) to a ticket. Use multipart/form-data.
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    file = request.FILES.get("file")
    if not file:
        return Response({"error": "No file uploaded."}, status=400)
    filename = default_storage.save(f"ticket_{ticket_id}/{file.name}", file)
    # Optionally, store file URL in ticket or as a TicketInteraction
    TicketInteraction.objects.create(
        ticket=ticket,
        user=ticket.user,
        interaction_type="user_message",
        content=f"Attachment uploaded: {filename}"
    )
    return Response({"message": "File uploaded.", "file_url": default_storage.url(filename)})

@api_view(["POST"])
def add_comment(request, ticket_id):
    """
    Add a comment to a ticket (threaded discussion).
    Body: {"comment": "..."}
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    comment = request.data.get("comment")
    if not comment:
        return Response({"error": "Comment is required."}, status=400)
    TicketInteraction.objects.create(
        ticket=ticket,
        user=ticket.user,
        interaction_type="user_message",
        content=f"Comment: {comment}"
    )
    return Response({"message": "Comment added."})

@api_view(["POST"])
def escalate_ticket(request, ticket_id):
    """
    Escalate a ticket for priority handling.
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    ticket.status = "escalated"
    ticket.save()
    TicketInteraction.objects.create(
        ticket=ticket,
        user=ticket.user,
        interaction_type="user_message",
        content="Ticket escalated by user."
    )
    return Response({"message": "Ticket escalated."})

@api_view(["POST"])
def assign_ticket(request, ticket_id):
    """
    Assign or reassign a ticket to an agent.
    Body: {"agent_id": "..."}
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    agent_id = request.data.get("agent_id")
    if not agent_id:
        return Response({"error": "agent_id is required."}, status=400)
    from users.models import User
    agent = get_object_or_404(User, user_id=agent_id)
    ticket.assigned_to = agent
    ticket.save()
    TicketInteraction.objects.create(
        ticket=ticket,
        user=agent,
        interaction_type="user_message",
        content="Ticket assigned to agent."
    )
    return Response({"message": f"Ticket assigned to {agent.name}."})

@api_view(["POST"])
def update_ticket_status(request, ticket_id):
    """
    Update ticket status (close, cancel, reopen, etc.).
    Body: {"status": "resolved"}
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    status_val = request.data.get("status")
    if not status_val:
        return Response({"error": "status is required."}, status=400)
    ticket.status = status_val
    ticket.save()
    TicketInteraction.objects.create(
        ticket=ticket,
        user=ticket.user,
        interaction_type="user_message",
        content=f"Status updated to {status_val}."
    )
    return Response({"message": f"Ticket status updated to {status_val}."})

@api_view(["GET"])
def agent_dashboard(request):
    """
    Agent/admin dashboard: summary of open/closed tickets, response times, performance, etc.
    """
    open_tickets = Ticket.objects.filter(status__in=["new", "in-progress", "escalated"]).count()
    closed_tickets = Ticket.objects.filter(status="resolved").count()
    avg_response = TicketInteraction.objects.filter(interaction_type="agent_response").aggregate(avg=Avg("created_at"))
    return Response({
        "open_tickets": open_tickets,
        "closed_tickets": closed_tickets,
        "avg_agent_response_time": avg_response["avg"],
    })

@api_view(["POST"])
def bulk_update_tickets(request):
    """
    Bulk update tickets (close, assign, etc.).
    Body: {"ticket_ids": [1,2,3], "status": "resolved"}
    """
    ids = request.data.get("ticket_ids", [])
    status_val = request.data.get("status")
    if not ids or not status_val:
        return Response({"error": "ticket_ids and status are required."}, status=400)
    Ticket.objects.filter(ticket_id__in=ids).update(status=status_val)
    return Response({"message": f"Updated {len(ids)} tickets to {status_val}."})

@api_view(["GET"])
def suggest_kb_articles(request, ticket_id):
    """
    Suggest relevant knowledge base articles for a ticket.
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    from knowledge_base.models import KnowledgeBaseArticle
    articles = KnowledgeBaseArticle.objects.filter(category=ticket.category)[:5]
    return Response({"suggestions": [a.title for a in articles]})

@api_view(["POST"])
def add_internal_note(request, ticket_id):
    """
    Add a private/internal note to a ticket (visible only to agents).
    Body: {"note": "..."}
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    note = request.data.get("note")
    if not note:
        return Response({"error": "Note is required."}, status=400)
    # Store as a special TicketInteraction type
    TicketInteraction.objects.create(
        ticket=ticket,
        user=ticket.assigned_to or ticket.user,
        interaction_type="agent_response",
        content=f"[INTERNAL NOTE] {note}"
    )
    return Response({"message": "Internal note added."})

@api_view(["GET"])
def audit_log(request, ticket_id):
    """
    Get audit log (all interactions) for a ticket.
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    interactions = TicketInteraction.objects.filter(ticket=ticket).order_by("created_at")
    serializer = TicketInteractionSerializer(interactions, many=True)
    return Response(serializer.data)

@api_view(["GET"])
def ai_suggestions(request, ticket_id):
    """
    Get AI-suggested solutions or similar tickets for a ticket.
    """
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    # Dummy implementation: return last 3 resolved tickets in same category
    similar = Ticket.objects.filter(category=ticket.category, status="resolved").exclude(ticket_id=ticket_id)[:3]
    return Response({"similar_tickets": TicketSerializer(similar, many=True).data})

# --- Documentation for all endpoints ---
"""
API Endpoints for Ticket Management (Web Portal)
===============================================

1. POST   /api/tickets/                       - Create a new ticket
2. GET    /api/tickets/                       - List all tickets (optionally filter by user/status)
3. GET    /api/tickets/<ticket_id>/           - Get details for a single ticket
4. PATCH  /api/tickets/<ticket_id>/           - Update ticket status/details
5. POST   /api/tickets/<ticket_id>/clarify/   - Add clarification to a ticket
6. POST   /api/tickets/<ticket_id>/feedback/  - Add feedback to a ticket
7. GET    /api/tickets/<ticket_id>/history/   - Get recent ticket interactions (history)
8. GET    /api/tickets/analytics/             - Ticket analytics
9. POST   /api/tickets/<ticket_id>/process/   - Manually trigger agent processing
10. GET   /api/tickets/tasks/<task_id>/status/ - Get Celery task status
11. GET   /api/tickets/<ticket_id>/agent-status/ - Get agent processing status and history
12. GET   /api/tickets/search/                 - Search and filter tickets
13. POST  /api/tickets/<ticket_id>/upload/    - Upload an attachment to a ticket
14. POST  /api/tickets/<ticket_id>/comment/   - Add a comment to a ticket
15. POST  /api/tickets/<ticket_id>/escalate/  - Escalate a ticket
16. POST  /api/tickets/<ticket_id>/assign/    - Assign a ticket to an agent
17. POST  /api/tickets/<ticket_id>/status/    - Update ticket status
18. GET   /api/tickets/agent-dashboard/        - Agent/admin dashboard
19. POST  /api/tickets/bulk-update/           - Bulk update tickets
20. GET   /api/tickets/<ticket_id>/kb-suggestions/ - Suggest knowledge base articles
21. POST  /api/tickets/<ticket_id>/internal-note/ - Add an internal note to a ticket
22. GET   /api/tickets/<ticket_id>/audit-log/ - Get audit log for a ticket
23. GET   /api/tickets/<ticket_id>/ai-suggestions/ - Get AI suggestions for a ticket

All endpoints return JSON responses. Authentication/permissions can be added as needed.
"""
