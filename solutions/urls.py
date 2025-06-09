from django.urls import path
from . import views

urlpatterns = [
    # Solution URLs
    path('', views.solution_list, name='solution_list'),
    path('create/', views.solution_create, name='solution_create'),
    path('<int:pk>/', views.solution_detail, name='solution_detail'),
    path('<int:pk>/update/', views.solution_update, name='solution_update'),
    path('<int:pk>/verify/', views.solution_verify, name='solution_verify'),
    
    # Knowledge Base URLs
    path('kb/', views.kb_entry_list, name='kb_entry_list'),
    path('kb/create/', views.kb_entry_create, name='kb_entry_create'),
    path('kb/<int:pk>/', views.kb_entry_detail, name='kb_entry_detail'),
    path('kb/<int:pk>/update/', views.kb_entry_update, name='kb_entry_update'),
    path('kb/<int:pk>/delete/', views.kb_entry_delete, name='kb_entry_delete'),
    path('kb/<int:pk>/verify/', views.kb_entry_verify, name='kb_entry_verify'),
]
