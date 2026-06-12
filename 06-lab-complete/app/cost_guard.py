"""Redis-backed monthly cost guard."""
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import redis_client


PRICE_PER_1K_INPUT_TOKENS = 0.00015
PRICE_PER_1K_OUTPUT_TOKENS = 0.0006


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1000 * PRICE_PER_1K_INPUT_TOKENS
        + output_tokens / 1000 * PRICE_PER_1K_OUTPUT_TOKENS
    )


def _usage_key(user_id: str) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"usage:{month}:{user_id}"


def get_usage(user_id: str) -> dict:
    key = _usage_key(user_id)
    try:
        raw = redis_client.hgetall(key)
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable")

    input_tokens = int(raw.get("input_tokens", 0))
    output_tokens = int(raw.get("output_tokens", 0))
    request_count = int(raw.get("request_count", 0))
    cost_usd = float(raw.get("cost_usd", 0.0))

    return {
        "user_id": user_id,
        "month": datetime.now(timezone.utc).strftime("%Y-%m"),
        "request_count": request_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 6),
        "budget_usd": settings.monthly_budget_usd,
        "remaining_usd": round(max(0.0, settings.monthly_budget_usd - cost_usd), 6),
    }


def check_budget(user_id: str, projected_cost_usd: float = 0.0) -> None:
    usage = get_usage(user_id)
    if usage["cost_usd"] + projected_cost_usd > settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Monthly budget exceeded",
                "used_usd": usage["cost_usd"],
                "projected_usd": round(projected_cost_usd, 6),
                "budget_usd": settings.monthly_budget_usd,
            },
        )


def record_usage(user_id: str, input_tokens: int, output_tokens: int) -> dict:
    cost = estimate_cost_usd(input_tokens, output_tokens)
    key = _usage_key(user_id)

    try:
        pipe = redis_client.pipeline()
        pipe.hincrby(key, "input_tokens", input_tokens)
        pipe.hincrby(key, "output_tokens", output_tokens)
        pipe.hincrby(key, "request_count", 1)
        pipe.hincrbyfloat(key, "cost_usd", cost)
        pipe.expire(key, 370 * 24 * 60 * 60)
        pipe.execute()
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable")

    return get_usage(user_id)
