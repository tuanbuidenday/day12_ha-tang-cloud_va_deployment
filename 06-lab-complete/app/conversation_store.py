"""Redis-backed conversation history."""
import json
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import redis_client


def _history_key(session_id: str) -> str:
    return f"conversation:{session_id}"


def append_message(session_id: str, role: str, content: str) -> list[dict]:
    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    key = _history_key(session_id)

    try:
        pipe = redis_client.pipeline()
        pipe.rpush(key, json.dumps(message, ensure_ascii=False))
        pipe.ltrim(key, -settings.max_history_messages, -1)
        pipe.expire(key, settings.conversation_ttl_seconds)
        pipe.execute()
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Conversation storage unavailable")

    return get_history(session_id)


def get_history(session_id: str) -> list[dict]:
    try:
        raw_messages = redis_client.lrange(_history_key(session_id), 0, -1)
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Conversation storage unavailable")
    return [json.loads(item) for item in raw_messages]
