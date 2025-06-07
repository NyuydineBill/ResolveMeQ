from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from celery.task.control import inspect
from tickets.models import Ticket
from tickets.tasks import process_ticket_with_agent
import json
from datetime import timedelta

class Command(BaseCommand):
    help = 'Manage and monitor AI agent tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            choices=['list', 'retry-failed', 'cleanup', 'stats'],
            help='Action to perform',
            required=True
        )
        parser.add_argument(
            '--ticket-id',
            type=int,
            help='Specific ticket ID to process (for retry-failed)'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to look back (for cleanup and stats)'
        )

    def handle(self, *args, **options):
        action = options['action']
        
        if action == 'list':
            self.list_tasks()
        elif action == 'retry-failed':
            self.retry_failed_tasks(options['ticket_id'])
        elif action == 'cleanup':
            self.cleanup_old_tasks(options['days'])
        elif action == 'stats':
            self.show_stats(options['days'])

    def list_tasks(self):
        """List all active and scheduled agent tasks"""
        i = inspect()
        
        # Get active tasks
        active = i.active() or {}
        scheduled = i.scheduled() or {}
        
        self.stdout.write("Active Tasks:")
        for worker, tasks in active.items():
            self.stdout.write(f"\nWorker: {worker}")
            for task in tasks:
                if task['name'] == 'tickets.tasks.process_ticket_with_agent':
                    self.stdout.write(
                        f"  - Task {task['id']}: Processing ticket {task['args']}"
                    )
        
        self.stdout.write("\nScheduled Tasks:")
        for worker, tasks in scheduled.items():
            self.stdout.write(f"\nWorker: {worker}")
            for task in tasks:
                if task['name'] == 'tickets.tasks.process_ticket_with_agent':
                    self.stdout.write(
                        f"  - Task {task['id']}: Processing ticket {task['args']} "
                        f"(ETA: {task['eta']})"
                    )

    def retry_failed_tasks(self, ticket_id=None):
        """Retry failed agent processing for tickets"""
        if ticket_id:
            tickets = Ticket.objects.filter(ticket_id=ticket_id)
        else:
            # Find tickets that failed processing
            tickets = Ticket.objects.filter(
                agent_processed=False,
                updated_at__lt=timezone.now() - timedelta(hours=1)
            )
        
        for ticket in tickets:
            self.stdout.write(f"Retrying agent processing for ticket {ticket.ticket_id}")
            process_ticket_with_agent.delay(ticket.ticket_id)

    def cleanup_old_tasks(self, days):
        """Clean up old agent processing attempts"""
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Find tickets that haven't been processed and are old
        old_tickets = Ticket.objects.filter(
            agent_processed=False,
            updated_at__lt=cutoff_date
        )
        
        count = old_tickets.count()
        self.stdout.write(f"Found {count} old unprocessed tickets")
        
        if count > 0:
            # Reset their processing status
            old_tickets.update(agent_response=None)
            self.stdout.write("Reset agent processing status for old tickets")

    def show_stats(self, days):
        """Show statistics about agent processing"""
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Get ticket stats
        total_tickets = Ticket.objects.filter(created_at__gte=cutoff_date).count()
        processed_tickets = Ticket.objects.filter(
            agent_processed=True,
            updated_at__gte=cutoff_date
        ).count()
        failed_tickets = Ticket.objects.filter(
            agent_processed=False,
            updated_at__gte=cutoff_date
        ).count()
        
        self.stdout.write(f"\nAgent Processing Stats (Last {days} days):")
        self.stdout.write(f"Total Tickets: {total_tickets}")
        self.stdout.write(f"Successfully Processed: {processed_tickets}")
        self.stdout.write(f"Failed/Unprocessed: {failed_tickets}")
        
        if total_tickets > 0:
            success_rate = (processed_tickets / total_tickets) * 100
            self.stdout.write(f"Success Rate: {success_rate:.1f}%")
        
        # Show recent agent responses
        recent_responses = Ticket.objects.filter(
            agent_processed=True,
            updated_at__gte=cutoff_date
        ).order_by('-updated_at')[:5]
        
        if recent_responses.exists():
            self.stdout.write("\nRecent Agent Responses:")
            for ticket in recent_responses:
                self.stdout.write(
                    f"\nTicket {ticket.ticket_id} ({ticket.updated_at}):"
                )
                self.stdout.write(
                    json.dumps(ticket.agent_response, indent=2)
                ) 