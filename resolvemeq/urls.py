from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
   openapi.Info(
      title="ResolveMeQ API",
      default_version='v1',
      description="API documentation for ResolveMeQ",
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/users/", include("users.urls")),
    path("api/tickets/", include("tickets.urls")),
    path("api/solutions/", include("solutions.urls")),
    path("api/knowledge_base/", include("knowledge_base.urls")),
    path("api/automation/", include("automation.urls")),
    path("api/core/", include("core.urls")),
    path("api/integrations/", include("integrations.urls")),
    path('docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
