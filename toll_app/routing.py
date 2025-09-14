from django.urls import re_path
from .consumer import LiveDetectionConsumer

websocket_urlpatterns = [
    re_path(r'ws/live-detection/$', LiveDetectionConsumer.as_asgi()),
]