import asyncio
import json
import os
import time
import uuid
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import aiohttp
import psutil
import requests
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from asgiref.sync import async_to_sync, sync_to_async
from channels.db import database_sync_to_async
from django import forms
from django.contrib import auth
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import redirect_to_login
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import redirect, render, resolve_url
from django.utils.decorators import classonlymethod, method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View

from chat.redis_ps import RedisPublisher
from searchapp.as_login_required import async_login_required

DEFAULT = "default"
loop = asyncio.get_event_loop()
rd = RedisPublisher()
executors = {DEFAULT: AsyncIOExecutor()}
scheduler = BackgroundScheduler()


class Index(View):
    async def get(self, request, *args, **kwargs):
        return redirect("search")


class Index_1(View):
    async def get(self, request, *args, **kwargs):
        return render(request, "index_1.html")


class SearchView(View):
    @classonlymethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        view._is_coroutine = asyncio.coroutines._is_coroutine
        return view

    @staticmethod
    @database_sync_to_async
    def set_session(request, key, value):
        request.session[key] = value
        request.session.save()

    @staticmethod
    @database_sync_to_async
    def get_session(request, key):
        return request.session.get(key, "")  # or return default key

    async def get_data(self, request):
        query = await SearchView.get_session(request, "query")
        context = {
            "users": await cache.aget("search_user", []),
            "query": query,
        }
        return context

    # @async_login_required(login_url="/login/")
    async def get(self, request, *args, **kwargs):
        context = await self.get_data(request)

        return render(request, "search.html", context)

    async def post(self, request, *args, **kwargs):
        return await self.search_data(request)

    @staticmethod
    async def action_search(request):
        print("Time sleep 5")
        await asyncio.sleep(3)
        print("Time sleep 5 done")
        query = request.POST.get("q", "")
        users = User.objects.filter(username__icontains=query)
        users = await database_sync_to_async(list)(users.values('username', 'email'))

        await cache.aset("search_user", users, timeout=10)
        await SearchView.set_session(request, "query", query)
        query_session = await SearchView.get_session(request, "query")
        print(users)
        print("ss", query_session)
        # channel = "notify_test"
        # message = {"message": "Hello, Redis!", "status": True}
        # rd.publish(channel, message)

    async def search_data(self, request):
        run_time = datetime.now() + timedelta(seconds=1)
        job_id = str(uuid.uuid4())

        scheduler.add_job(
            async_to_sync(SearchView.action_search),
            "date",
            run_date=run_time,
            id=job_id,
            args=[request],
        )
        if not scheduler.running:
            scheduler.start()

        return HttpResponse(json.dumps({"status": "ok"}))

    async def test_post(self, *args, **kwargs):
        mehtod = self.method
        arg = kwargs
        return HttpResponse(
            json.dumps(
                {
                    "status": "ok",
                    "mehtod": mehtod,
                    "arg": arg,
                }
            )
        )

    async def test_post_view(request, *args, **kwargs):
        return await SearchView.test_post(request, **kwargs)

    async def update_async_data(self, *args, **kwargs):
        search_user = await cache.aget("search_user", [])
        query = await SearchView.get_session(self, "query")

        return HttpResponse(
            json.dumps(
                {
                    "status": "ok",
                    "search_user": str(search_user),
                    "query": query,
                }
            )
        )

    async def action_update_data(request, *args, **kwargs):
        return await SearchView.update_async_data(request, **kwargs)

    async def fetch(session, url):
        async with session.get(url) as response:
            return await response.json()

    async def fetch_all(urls):
        async with aiohttp.ClientSession() as session:
            tasks = []
            for url in urls:
                tasks.append(SearchView.fetch(session, url))
            responses = await asyncio.gather(*tasks)
        return responses

    async def async_request(request, *args, **kwargs):
        url = "https://jsonplaceholder.typicode.com/todos/"
        urls = []
        for i in range(1, 100):
            urls.append(url + f"{i}")

        responses = await SearchView.fetch_all(urls)

        return JsonResponse({"data": responses})


async def stream_messages_view(request):
    async def event_stream():
        body = f"data: {datetime.now()}\n"
        body_len = len(body)
        print(body_len)
        initial_data = None
        user = await sync_to_async(auth.get_user)(request)
        print(user.pk)
        query = ""
        print(query)
        count = 0
        while True:
            body = f"data: date-{datetime.now()}\n"
            data = await cache.aget("search_user", [])
            query = await SearchView.get_session(request, "query")
            if not initial_data == data and data:
                yield "\ndata: {}-{}\n\n".format(data, query)
                initial_data = data
            else:
                yield f"data: {count}\n\n"
                count = count + 1
                count = 0 if count == 101 else count

            await asyncio.sleep(2)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'

    return response


def clear_cache_session(request):
    try:
        cache.clear()
        del request.session["query"]
    except KeyError:
        pass
    return HttpResponse(json.dumps({"status": "ok"}))


class LoginForm(forms.Form):
    email = forms.CharField(
        label="Email",
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    password = forms.CharField(
        label="Password",
        required=True,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)


class LoginView(View):
    async def get(self, request, *args, **kwargs):
        form = LoginForm(request.GET)
        context = {"form": form}
        return render(request, "login.html", context)

    async def post(self, request, *args, **kwargs):
        r = request.POST
        return HttpResponse(json.dumps({"status": "ok", "data": r}))


# A decorator that prints the memory usage before and after calling a function
def cpu_ram_usage(func):
    def wrapper(*args, **kwargs):
        # Get the current process
        process = psutil.Process(os.getpid())
        # Get the CPU and RAM usage before calling the function
        cpu_before = process.cpu_percent()
        ram_before = process.memory_info().rss / 1024 ** 2
        # Call the function and get the result
        result = func(*args, **kwargs)
        # Get the CPU and RAM usage after calling the function
        cpu_after = process.cpu_percent()
        ram_after = process.memory_info().rss / 1024 ** 2
        # Print the CPU and RAM usage difference
        print(f"CPU used by {func.__name__}: {cpu_after - cpu_before} %")
        print(f"RAM used by {func.__name__}: {ram_after - ram_before} MB")
        # Return the result
        return result
    return wrapper


@csrf_exempt
@cpu_ram_usage
def long_polling_view(request, *args, **kwargs):
    # Simulate waiting for an event to occur
    time.sleep(3)
    data = request.session.get("query")
    bar = int(request.GET.get("test"))
    bar = bar + 1
    data2 = cache.get("search_user", [])
    if bar == 101:
        bar = 0
    # Once the event has occurred, return a response
    return JsonResponse({'message': f'Event occurred {data}', "data": bar, "data2": data2})
