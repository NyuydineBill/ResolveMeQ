from django.urls import path
from .views import HelloUser

urlpatterns = [
    path("hello/", HelloUser.as_view(), name="hello-user"),
]
