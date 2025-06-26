from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import KnowledgeBaseArticleViewSet, LLMResponseViewSet, kb_articles_for_agent, search_kb_for_agent, kb_article_by_id

router = DefaultRouter()
router.register(r'articles', KnowledgeBaseArticleViewSet)
router.register(r'responses', LLMResponseViewSet)

urlpatterns = [
    path('', include(router.urls)),
    # API endpoints for FastAPI agent
    path('api/articles/', kb_articles_for_agent, name='kb-articles-for-agent'),
    path('api/search/', search_kb_for_agent, name='search-kb-for-agent'),
    path('api/articles/<str:kb_id>/', kb_article_by_id, name='kb-article-by-id'),
]
