"""Production AI Agent combining Day 12 deployment concepts."""
import json
import logging
import signal
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.auth import verify_api_key
from app.config import settings
from app.conversation_store import append_message, get_history
from app.cost_guard import check_budget, estimate_cost_usd, get_usage, record_usage
from app.rate_limiter import check_rate_limit
from app.redis_client import ping_redis
from utils.mock_llm import ask as llm_ask


logging.basicConfig(
    level=logging.DEBUG if settings.debug else getattr(logging, settings.log_level.upper(), logging.INFO),
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
INSTANCE_ID = f"agent-{uuid.uuid4().hex[:8]}"
_is_ready = False
_request_count = 0
_error_count = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "instance_id": INSTANCE_ID,
    }))

    _is_ready = ping_redis()
    if not _is_ready:
        logger.error(json.dumps({"event": "redis_unavailable", "redis_url": settings.redis_url}))
    else:
        logger.info(json.dumps({"event": "ready", "storage": "redis"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown", "instance_id": INSTANCE_ID}))


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Instance-ID"] = INSTANCE_ID
        if "server" in response.headers:
            del response.headers["server"]
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": round((time.time() - start) * 1000, 1),
            "instance_id": INSTANCE_ID,
        }))
        return response
    except Exception:
        _error_count += 1
        raise


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field("default-user", min_length=1, max_length=128)
    session_id: str | None = Field(None, max_length=128)


class AskResponse(BaseModel):
    session_id: str
    user_id: str
    question: str
    answer: str
    model: str
    turn: int
    history_count: int
    usage: dict
    served_by: str
    timestamp: str


@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "instance_id": INSTANCE_ID,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "history": "GET /sessions/{session_id}/history (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _auth: str = Depends(verify_api_key),
):
    global _is_ready
    _is_ready = ping_redis()
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Service is not ready")

    rate = check_rate_limit(body.user_id)
    session_id = body.session_id or str(uuid.uuid4())
    input_tokens = max(1, len(body.question.split()) * 2)
    projected_input_cost = estimate_cost_usd(input_tokens, 0)
    check_budget(body.user_id, projected_input_cost)

    append_message(session_id, "user", body.question)

    logger.info(json.dumps({
        "event": "agent_call",
        "user_id": body.user_id,
        "session_id": session_id,
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
        "rate_remaining": rate["remaining"],
    }))

    answer = llm_ask(body.question)
    output_tokens = max(1, len(answer.split()) * 2)
    projected_total_cost = estimate_cost_usd(input_tokens, output_tokens)
    check_budget(body.user_id, projected_total_cost)
    usage = record_usage(body.user_id, input_tokens, output_tokens)
    history = append_message(session_id, "assistant", answer)
    turn = len([message for message in history if message["role"] == "user"])

    return AskResponse(
        session_id=session_id,
        user_id=body.user_id,
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        turn=turn,
        history_count=len(history),
        usage=usage,
        served_by=INSTANCE_ID,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/sessions/{session_id}/history", tags=["Agent"])
def session_history(session_id: str, _auth: str = Depends(verify_api_key)):
    history = get_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return {
        "session_id": session_id,
        "messages": history,
        "count": len(history),
        "served_by": INSTANCE_ID,
    }


@app.get("/health", tags=["Operations"])
def health():
    redis_ok = ping_redis()
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": {
            "llm": "mock" if not settings.openai_api_key else "openai",
            "redis": "ok" if redis_ok else "unavailable",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    global _is_ready
    _is_ready = ping_redis()
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Redis not available")
    return {"ready": True, "instance_id": INSTANCE_ID, "storage": "redis"}


@app.get("/metrics", tags=["Operations"])
def metrics(user_id: str = "default-user", _auth: str = Depends(verify_api_key)):
    usage = get_usage(user_id)
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "instance_id": INSTANCE_ID,
        "usage": usage,
    }


def _handle_signal(signum, _frame):
    global _is_ready
    _is_ready = False
    logger.info(json.dumps({"event": "signal", "signum": signum, "ready": False}))


signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
