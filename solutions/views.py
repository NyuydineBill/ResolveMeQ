from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.db import models
from .models import Solution, KnowledgeBaseEntry
from .serializers import (
    SolutionSerializer,
    KnowledgeBaseEntrySerializer,
    KnowledgeBaseEntryListSerializer
)

# Create your views here.

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def solution_list(request):
    """
    List all solutions with optional filtering
    """
    queryset = Solution.objects.all()
    
    # Filter by worked status
    worked = request.query_params.get('worked')
    if worked is not None:
        worked = worked.lower() == 'true'
        queryset = queryset.filter(worked=worked)
    
    # Filter by ticket
    ticket_id = request.query_params.get('ticket_id')
    if ticket_id:
        queryset = queryset.filter(ticket_id=ticket_id)
    
    serializer = SolutionSerializer(queryset, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def solution_detail(request, pk):
    """
    Retrieve a specific solution
    """
    solution = get_object_or_404(Solution, pk=pk)
    serializer = SolutionSerializer(solution)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def solution_create(request):
    """
    Create a new solution
    """
    serializer = SolutionSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def solution_update(request, pk):
    """
    Update a solution
    """
    solution = get_object_or_404(Solution, pk=pk)
    serializer = SolutionSerializer(solution, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def solution_verify(request, pk):
    """
    Verify a solution (admin only)
    """
    solution = get_object_or_404(Solution, pk=pk)
    solution.verified_by = request.user
    solution.verification_date = timezone.now()
    solution.save()
    
    serializer = SolutionSerializer(solution)
    return Response(serializer.data)

# Knowledge Base API Views

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def kb_entry_list(request):
    """
    List all knowledge base entries with optional filtering
    """
    queryset = KnowledgeBaseEntry.objects.all()
    
    # Filter by category
    category = request.query_params.get('category')
    if category:
        queryset = queryset.filter(category=category)
    
    # Filter by verified status
    verified = request.query_params.get('verified')
    if verified is not None:
        verified = verified.lower() == 'true'
        queryset = queryset.filter(verified=verified)
    
    # Filter by search term
    search = request.query_params.get('search')
    if search:
        queryset = queryset.filter(
            models.Q(issue_type__icontains=search) |
            models.Q(description__icontains=search) |
            models.Q(solution__icontains=search) |
            models.Q(tags__icontains=search)
        )
    
    # Order by confidence score and usage count
    queryset = queryset.order_by('-confidence_score', '-usage_count')
    
    serializer = KnowledgeBaseEntryListSerializer(queryset, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def kb_entry_detail(request, pk):
    """
    Retrieve a specific knowledge base entry
    """
    entry = get_object_or_404(KnowledgeBaseEntry, pk=pk)
    
    # Update usage statistics
    entry.usage_count += 1
    entry.last_used = timezone.now()
    entry.save()
    
    serializer = KnowledgeBaseEntrySerializer(entry)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def kb_entry_create(request):
    """
    Create a new knowledge base entry (admin only)
    """
    serializer = KnowledgeBaseEntrySerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT', 'PATCH'])
@permission_classes([IsAdminUser])
def kb_entry_update(request, pk):
    """
    Update a knowledge base entry (admin only)
    """
    entry = get_object_or_404(KnowledgeBaseEntry, pk=pk)
    serializer = KnowledgeBaseEntrySerializer(entry, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def kb_entry_delete(request, pk):
    """
    Delete a knowledge base entry (admin only)
    """
    entry = get_object_or_404(KnowledgeBaseEntry, pk=pk)
    entry.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def kb_entry_verify(request, pk):
    """
    Verify a knowledge base entry (admin only)
    """
    entry = get_object_or_404(KnowledgeBaseEntry, pk=pk)
    entry.verified = True
    entry.verified_by = request.user
    entry.verification_date = timezone.now()
    entry.save()
    
    serializer = KnowledgeBaseEntrySerializer(entry)
    return Response(serializer.data)
