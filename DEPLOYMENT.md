# Deployment Information

## Public URL
https://ai-agent-production-n3l0.onrender.com

## Platform
Render (Docker web service `plan: free` + Render Key Value for Redis), region Singapore.
Blueprint: [render.yaml](render.yaml) at repo root with `rootDir: 06-lab-complete`.

> Note: Render free instances sleep after ~15 min idle; the first request after
> sleeping takes ~30–50s (cold start), then responses are fast.

## Live Test Commands (production URL)

### Health check
```bash
curl https://ai-agent-production-n3l0.onrender.com/health
# {"status":"ok","environment":"production","instance_id":"agent-...","checks":{"llm":"openai","redis":"ok"}}
```

### Readiness check
```bash
curl https://ai-agent-production-n3l0.onrender.com/ready
# {"ready":true,"storage":"redis"}
```

### Auth required (no key → 401)
```bash
curl -X POST https://ai-agent-production-n3l0.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'
# HTTP 401
```

### API test with authentication (use the AGENT_API_KEY from Render dashboard)
```bash
curl -X POST https://ai-agent-production-n3l0.onrender.com/ask \
  -H "X-API-Key: <AGENT_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"student1","question":"Hello"}'
```

### Rate limiting (eventually 429)
```bash
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    https://ai-agent-production-n3l0.onrender.com/ask \
    -H "X-API-Key: <AGENT_API_KEY>" -H "Content-Type: application/json" \
    -d '{"user_id":"rate-test","question":"test"}'
done
```

## Live Deployment Verification (production URL)

Tested against https://ai-agent-production-n3l0.onrender.com :

| Endpoint | Result |
|----------|--------|
| `GET /health` | `200 {"status":"ok","environment":"production","checks":{"llm":"openai","redis":"ok"}}` ✅ |
| `GET /ready` | `200 {"ready":true,"storage":"redis"}` ✅ |
| `GET /` | `200` (app info + endpoint list) ✅ |
| `POST /ask` (no key) | `401` ✅ |

Redis is connected in production (`checks.redis: "ok"`, `/ready storage: "redis"`) — state
(rate limit, cost guard, conversation history) is shared, so the app is horizontally scalable.

## Local Test Commands (docker compose)

```bash
cd 06-lab-complete
docker compose up --scale agent=3            # 3 agents + redis + nginx (LB at :8080)
curl http://localhost:8080/health
curl http://localhost:8080/ready
curl -X POST http://localhost:8080/ask \
  -H "X-API-Key: dev-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"student1","question":"Hello"}'
```

## Screenshots
- [Render dashboard — deploy live, Docker/Free/Blueprint](screenshots/dashboard.png)
- [Service running — production JSON response](screenshots/running.png)
- [Logs — structured JSON, GET /health 200 OK](screenshots/test.png)

## Environment Variables Set (on Render)
- `PORT`
- `REDIS_URL`
- `AGENT_API_KEY`
- `JWT_SECRET`
- `LOG_LEVEL`
- `RATE_LIMIT_PER_MINUTE`
- `RATE_LIMIT_WINDOW_SECONDS`
- `MONTHLY_BUDGET_USD`
- `CONVERSATION_TTL_SECONDS`
- `MAX_HISTORY_MESSAGES`

## Verification Status

`python3 06-lab-complete/check_production_ready.py`: **20/20 checks passed (100%)**.

Full stack was built and run locally with `docker compose up --scale agent=3` (3 agents + redis + nginx). All requirements verified end-to-end:

| Check | Result |
|-------|--------|
| Production image size (< 500 MB) | **332 MB** ✅ (dev single-stage image was 1.67 GB → ~80% smaller) |
| `GET /health` | `200 {"status":"ok",...}` ✅ |
| `GET /ready` | `200 {"ready":true,...}` ✅ |
| `POST /ask` without API key | `401` ✅ |
| `POST /ask` with valid key | `200` + answer/usage ✅ |
| Rate limiting (10/min) | `200` ×10 then `429` on 11th ✅ |
| Cost guard | `402` when monthly budget exceeded ✅ |
| Load balancing | round-robin across all 3 instances (nginx `X-Upstream-Agent`) ✅ |
| Stateless | one conversation served by 3 different instances, full history in Redis ✅ |

Note: a bug was fixed during verification — `MutableHeaders.pop()` does not exist in Starlette; the security-header middleware now uses `del response.headers["server"]`.
