import redis.asyncio as aioredis
from app.config import settings

redis_client = None


async def get_redis():
    global redis_client
    if redis_client is None:
        try:
            redis_client = aioredis.from_url(
                settings.redis_url, decode_responses=True
            )
            await redis_client.ping()
        except Exception:
            redis_client = False  # Mark as unavailable
    return redis_client if redis_client is not False else None
