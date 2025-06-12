from rest_framework import serializers
from .models import Solution, KnowledgeBaseEntry, Ticket, TicketInteraction

class SolutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Solution
        fields = [
            'id', 'ticket', 'resolution', 'worked',
            'created_by', 'verified_by', 'verification_date',
            'confidence_score', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

class KnowledgeBaseEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeBaseEntry
        fields = [
            'id', 'ticket', 'issue_type', 'description',
            'solution', 'category', 'tags', 'confidence_score',
            'verified', 'verified_by', 'verification_date',
            'created_at', 'updated_at', 'last_used', 'usage_count'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'last_used', 'usage_count'
        ]

class KnowledgeBaseEntryListSerializer(serializers.ModelSerializer):
    """
    A simplified serializer for listing KB entries
    """
    class Meta:
        model = KnowledgeBaseEntry
        fields = [
            'id', 'issue_type', 'category', 'confidence_score',
            'verified', 'usage_count', 'last_used'
        ]

class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = [
            'ticket_id', 'user', 'issue_type', 'status', 'description', 'screenshot',
            'assigned_to', 'category', 'tags', 'created_at', 'updated_at', 'agent_response', 'agent_processed'
        ]
        read_only_fields = ['ticket_id', 'created_at', 'updated_at', 'agent_response', 'agent_processed']

class TicketInteractionSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    class Meta:
        model = TicketInteraction
        fields = ['id', 'ticket', 'user', 'interaction_type', 'content', 'created_at']
        read_only_fields = ['id', 'created_at']