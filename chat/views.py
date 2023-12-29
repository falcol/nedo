import asyncio
import contextlib
import json
import os

import aioredis
import async_timeout
from channels.generic.websocket import AsyncWebsocketConsumer
from dotenv import load_dotenv

load_dotenv()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"chat_{self.room_name}"

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()
        tsk = asyncio.create_task(self.pubsub())
        await tsk

        print(f"Joined chat room {self.room_name}")
        print(f"Joined chat group: {self.room_group_name}")

    async def pubsub(self):
        self.redis = aioredis.Redis.from_url(
            os.getenv("REDIS_URL"), decode_responses=True
        )
        self.psub = self.redis.pubsub()

        async def reader(channel: aioredis.client.PubSub):
            while True:
                with contextlib.suppress(asyncio.TimeoutError):
                    async with async_timeout.timeout(1):
                        message = await channel.get_message(ignore_subscribe_messages=True)
                        if message is not None:
                            message_data = message['data']
                            await self.send(text_data=message_data)
                        await asyncio.sleep(0.01)

        async with self.psub as p:
            await p.subscribe(f"notify_{self.room_name}")
            await reader(p)  # wait for reader to complete
            await p.unsubscribe(f"notify_{self.room_name}")

        # closing all open connections
        await self.psub.close()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        await self.close()
        await self.redis.close()
        await self.psub.close()

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)

        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name, {"type": "notify_message", "data": text_data_json}
        )

    # Receive message from room group
    async def chat_message(self, event):
        message = event["data"]

        # Send message to WebSocket
        await self.send(text_data=json.dumps(message))
