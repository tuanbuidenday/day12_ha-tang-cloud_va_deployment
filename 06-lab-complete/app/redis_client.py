"""Shared Redis client helpers."""
import redis

from app.config import settings


redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def ping_redis() -> bool:
    try:
        return bool(redis_client.ping())
    except redis.RedisError:
        return False
