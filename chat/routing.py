from django.urls import path

from .views import ChatConsumer

websocket_urlpatterns = [
    path('chat/<room_name>', ChatConsumer.as_asgi(), name='chat')
]
