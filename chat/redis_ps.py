import json
import os

import aioredis
import redis
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("REDIS_HOST")
PORT = os.getenv("REDIS_PORT")
class AsyncRedisPublisher:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.redis = None

    async def connect(self):
        self.redis = await aioredis.create_redis(f'redis://{self.host}:{self.port}')

    async def publish(self, channel, message):
        if not self.redis:
            await self.connect()

        # Publish a message to the channel
        await self.redis.publish(channel, json.dumps(message))
        await self.close()

    async def close(self):
        self.redis.close()


class RedisPublisher:
    def __init__(self, host=HOST, port=PORT, db=0):
        self.redis_client = redis.StrictRedis(host=host, port=port, db=db)

    def publish(self, channel_name, message):
        try:
            self.redis_client.publish(channel_name, json.dumps(message))
            self.close()
            print(f"Published '{message}' to '{channel_name}' channel")
        except Exception as e:
            print(f"Error publishing to '{channel_name}' channel: {str(e)}")

    def close(self):
        self.redis_client.close()
