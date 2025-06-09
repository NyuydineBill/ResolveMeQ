from rest_framework import serializers
from .models import KnowledgeBaseArticle, LLMResponse

class KnowledgeBaseArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeBaseArticle
        fields = ['kb_id', 'title', 'content', 'tags', 'created_at', 'updated_at', 
                 'views', 'helpful_votes', 'total_votes']
        read_only_fields = ['kb_id', 'created_at', 'updated_at', 'views', 
                           'helpful_votes', 'total_votes']

class LLMResponseSerializer(serializers.ModelSerializer):
    helpfulness_score = serializers.FloatField(read_only=True)
    related_kb_articles = KnowledgeBaseArticleSerializer(many=True, read_only=True)

    class Meta:
        model = LLMResponse
        fields = ['response_id', 'query', 'response', 'response_type', 'created_at',
                 'helpful_votes', 'total_votes', 'helpfulness_score', 
                 'related_kb_articles', 'ticket']
        read_only_fields = ['response_id', 'created_at', 'helpful_votes', 
                           'total_votes', 'helpfulness_score'] 