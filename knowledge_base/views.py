from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .models import KnowledgeBaseArticle, LLMResponse
from .serializers import KnowledgeBaseArticleSerializer, LLMResponseSerializer
from .services import KnowledgeBaseService
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)

class KnowledgeBaseArticleViewSet(viewsets.ModelViewSet):
    queryset = KnowledgeBaseArticle.objects.all()
    serializer_class = KnowledgeBaseArticleSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    lookup_field = 'kb_id'

    @action(detail=False, methods=['post'])
    def search(self, request):
        query = request.data.get('query', '')
        if not query:
            return Response({'error': 'Query parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        articles = self.queryset.filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(tags__contains=[query])
        ).order_by('-views', '-helpful_votes')

        serializer = self.get_serializer(articles, many=True)
        return Response({'results': serializer.data})

    @action(detail=True, methods=['post'])
    def rate(self, request, kb_id=None):
        article = self.get_object()
        is_helpful = request.data.get('is_helpful', None)
        
        if is_helpful is None:
            return Response({'error': 'is_helpful parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        article.total_votes += 1
        if is_helpful:
            article.helpful_votes += 1
        article.save()

        return Response({'status': 'success'})

class LLMResponseViewSet(viewsets.ModelViewSet):
    queryset = LLMResponse.objects.all()
    serializer_class = LLMResponseSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'response_id'

    def create(self, request, *args, **kwargs):
        try:
            response = KnowledgeBaseService.store_llm_response(
                query=request.data.get('query'),
                response=request.data.get('response'),
                response_type=request.data.get('response_type'),
                ticket=request.data.get('ticket'),
                related_kb_articles=request.data.get('related_kb_articles')
            )
            serializer = self.get_serializer(response)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error creating LLM response: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def rate(self, request, response_id=None):
        try:
            response = self.get_object()
            is_helpful = request.data.get('is_helpful')
            
            if is_helpful is None:
                return Response({'error': 'is_helpful parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

            updated_response = KnowledgeBaseService.update_response_rating(response.response_id, is_helpful)
            serializer = self.get_serializer(updated_response)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error rating LLM response: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def search(self, request):
        query = request.data.get('query', '')
        if not query:
            return Response({'error': 'Query parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        responses = KnowledgeBaseService.get_related_responses(query)
        serializer = self.get_serializer(responses, many=True)
        return Response({'results': serializer.data})
