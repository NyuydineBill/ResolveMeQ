from django.shortcuts import render
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField
from django.db.models.functions import TruncWeek
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Ticket

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
