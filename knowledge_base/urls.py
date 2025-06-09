from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import KnowledgeBaseArticleViewSet, LLMResponseViewSet

router = DefaultRouter()
router.register(r'articles', KnowledgeBaseArticleViewSet)
router.register(r'responses', LLMResponseViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
