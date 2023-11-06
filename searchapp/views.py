import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import aiohttp
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

    # @async_login_required(login_url="/index_1/")
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
        users = await database_sync_to_async(list)(users.values())

        await cache.aset("search_user", users, timeout=10)
        await SearchView.set_session(request, "query", query)
        print(users)
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
    async def event_stream(request):
        body = f"data: {datetime.now()}\n"
        body_len = len(body)
        print(body_len)
        initial_data = None
        user = await sync_to_async(auth.get_user)(request)
        print(user.pk)

        while True:
            body = f"data: {datetime.now()}\n"
            data = await cache.aget("search_user", [])
            if not initial_data == data:
                yield "\ndata: {}\n\n".format(data)
                initial_data = data
            await asyncio.sleep(2)

    # Create a new streaming task and store it in the request object
    current_stream_task = event_stream(request)

    return StreamingHttpResponse(current_stream_task, content_type="text/event-stream")




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
