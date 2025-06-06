from django.contrib import admin
from .models import Ticket
from integrations.models import SlackToken
from integrations.views import notify_user_ticket_resolved
import requests
import csv
from django.http import HttpResponse

@admin.action(description="Mark selected tickets as resolved")
def mark_as_resolved(modeladmin, request, queryset):
    for ticket in queryset:
        queryset.filter(pk=ticket.pk).update(status="resolved")
        if ticket.user and hasattr(ticket.user, "user_id"):
            notify_user_ticket_resolved(ticket.user.user_id, ticket.ticket_id)

@admin.action(description="Respond via Slack bot")
def respond_via_bot(modeladmin, request, queryset):
    token_obj = SlackToken.objects.order_by("-created_at").first()
    if not token_obj:
        return
    for ticket in queryset:
        if ticket.user and hasattr(ticket.user, "user_id"):
            headers = {
                "Authorization": f"Bearer {token_obj.access_token}",
                "Content-Type": "application/json",
            }
            reply_data = {
                "channel": ticket.user.user_id,  # Slack user_id as channel for DM
                "text": f"IT has responded to your ticket: {ticket.issue_type}\nStatus: {ticket.status}\nDescription: {ticket.description}",
            }
            requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=reply_data)

@admin.action(description="Export selected tickets as CSV")
def export_tickets_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="tickets.csv"'
    writer = csv.writer(response)
    writer.writerow(['Ticket ID', 'User', 'Issue Type', 'Status', 'Description', 'Screenshot', 'Created At', 'Updated At'])
    for ticket in queryset:
        writer.writerow([
            ticket.ticket_id,
            ticket.user.name if ticket.user else "",
            ticket.issue_type,
            ticket.status,
            ticket.description,
            ticket.screenshot,
            ticket.created_at,
            ticket.updated_at,
        ])
    return response

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "ticket_id", "user", "issue_type", "category", "status", "assigned_to", "description", "tags", "created_at", "updated_at"
    )
    list_filter = ("status", "assigned_to", "category")
    search_fields = (
        "user__user_id",
        "user__name",
        "user__email",
        "assigned_to__user_id",
        "assigned_to__name",
        "assigned_to__email",
        "issue_type",
        "description",
        "category",
        "tags",
    )
    actions = [mark_as_resolved, respond_via_bot, export_tickets_csv]
    autocomplete_fields = ["user", "assigned_to"]
