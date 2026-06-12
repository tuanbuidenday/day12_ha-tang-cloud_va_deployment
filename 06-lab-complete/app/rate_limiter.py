"""Redis-backed sliding-window rate limiter."""
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import redis_client


def check_rate_limit(user_id: str) -> dict:
    now = time.time()
    window_start = now - settings.rate_limit_window_seconds
    key = f"rate:{user_id}"
    member = f"{now}:{uuid.uuid4().hex}"

    try:
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {member: now})
        pipe.expire(key, settings.rate_limit_window_seconds)
        _, current_count, _, _ = pipe.execute()
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter storage unavailable")

    if current_count >= settings.rate_limit_per_minute:
        redis_client.zrem(key, member)
        retry_after = settings.rate_limit_window_seconds
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": settings.rate_limit_per_minute,
                "window_seconds": settings.rate_limit_window_seconds,
            },
            headers={
                "X-RateLimit-Limit": str(settings.rate_limit_per_minute),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(retry_after),
            },
        )

    remaining = settings.rate_limit_per_minute - current_count - 1
    return {
        "limit": settings.rate_limit_per_minute,
        "remaining": max(0, remaining),
        "window_seconds": settings.rate_limit_window_seconds,
    }
