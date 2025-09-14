from django.contrib import admin
from django.urls import path, include
from . import views
from decimal import Decimal

urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('admin-dash/', views.admin_dashboard, name='admin_dashboard'),

    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('sign-up/', views.signup, name='signup'),
    path('logout/', views.logout_view, name='logout'),

    # User functionalities
    path('api/recharge/', views.recharge_account, name='api_recharge'),
    path('api/history/', views.history, name='api_history'),
    path('manual-entry/', views.manual_entry, name='manual_entry'),
    path('video-entry/', views.process_video, name='video_entry'),

    # Live detection URLs
    path('live-detection/', views.live_detect, name='live_detection'),
    path('video-feed/', views.video_feed, name='video_feed'),
    path('api/detected-plates/', views.get_detected_plates, name='get_detected_plates'),
    path('api/process-frame/', views.process_single_frame, name='process_single_frame'),
    path('api/start-detection/', views.start_detection, name='start_detection'),
    path('api/stop-detection/', views.stop_detection, name='stop_detection')
]
