from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('sign-up/', views.signup, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('admin-dash/', views.admin_dashboard, name='admin_dashboard'),
    path('history/', views.history, name='history'),
    path('manual-entry/', views.manual_entry, name='manual_entry'),
    path('live-detect/', views.live_detect, name='live_detect'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Future implementations
    # path('user-history/', views.user_history, name='user_history'),
    # path('add-funds/<decimal:fund>', views.user_history, name='user_history'),
]
