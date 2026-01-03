"""Redis connection management."""

import redis.asyncio as redis

from app.core.config import settings

redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get Redis client instance."""
    global redis_client
    if redis_client is None:
        redis_client = await redis.from_url(settings.redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
    return redis_client


async def close_redis() -> None:
    """Close Redis connection."""
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        redis_client = None
