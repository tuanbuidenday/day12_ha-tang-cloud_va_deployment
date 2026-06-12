# Deployment Information

## Public URL
TODO: deploy to Railway or Render and paste the public URL here.

## Platform
Prepared for Railway or Render.

## Local Test Commands

### Start stack
```bash
cd 06-lab-complete
docker compose up --scale agent=3
```

### Health check
```bash
curl http://localhost:8080/health
```

### Readiness check
```bash
curl http://localhost:8080/ready
```

### API test with authentication
```bash
curl -X POST http://localhost:8080/ask \
  -H "X-API-Key: dev-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"student1","question":"Hello"}'
```

### Rate limiting test
```bash
for i in $(seq 1 15); do
  curl -X POST http://localhost:8080/ask \
    -H "X-API-Key: dev-key-change-me-in-production" \
    -H "Content-Type: application/json" \
    -d '{"user_id":"student-rate-test","question":"test"}'
done
```

## Environment Variables Set
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
