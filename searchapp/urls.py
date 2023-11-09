from django.http import HttpRequest
from django.urls import path

from .views import (
    Index,
    Index_1,
    LoginView,
    SearchView,
    clear_cache_session,
    long_polling_view,
    stream_messages_view,
)

urlpatterns = [
    path('', Index.as_view(), name='index'),
    # path('search_data/', search_view.search_data, name='search_data'),
    path('index_1/', Index_1.as_view(), name='index_1'),
    path('search/', SearchView.as_view(), name='search'),
    path('test_post/<str:name>', SearchView.test_post_view, name='test_post'),
    path('async_request/', SearchView.async_request, name='async_request'),
    path('action_update_data/', SearchView.action_update_data, name='action_update_data'),
    path('login/', LoginView.as_view(), name='LoginView'),
    path('stream/', stream_messages_view, name='stream'),
    path('clear_cache_session/', clear_cache_session, name='clear_cache_session'),
    path('long_polling_view/', long_polling_view, name='long_polling_view'),
]
