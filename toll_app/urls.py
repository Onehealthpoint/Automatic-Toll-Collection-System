from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('', views.index, name='index'),
    path('/login', views.login, name='login'),
    path('/sign-up', views.sign_up, name='sign_up'),
    path('/user/<uuid:user_id>/', views.user_dashboard, name='user_dashboard'),
    path('/user/history/<uuid:user_id>/', views.user_dashboard, name='user_dashboard'),
    path('/dashboard', views.admin_dashboard, name='admin_dashboard'),
    path('/history', views.history, name='history'),
    path('/manual-entry', views.manual_entry, name='manual_entry'),
    path('/auto-detect', views.auto_detect, name='auto_detect'),
]
