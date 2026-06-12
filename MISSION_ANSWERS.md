# Day 12 Lab - Mission Answers

> Student: Bùi Văn Tuân — ID 2A202601006
> All exercises below were verified by actually running the code (FastAPI apps + Docker stacks) on the machine. Real outputs are pasted in code blocks.

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (in `01-localhost-vs-production/develop/app.py`)
1. **Hardcoded secrets** — `OPENAI_API_KEY = "sk-..."` and `DATABASE_URL` with a password are committed in code. Push to GitHub = leaked instantly.
2. **Secret leaked to logs** — `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` writes the key to stdout.
3. **`print()` instead of structured logging** — no levels, no JSON, impossible to aggregate/search in production.
4. **No config management** — `DEBUG = True`, `MAX_TOKENS = 500` hardcoded; can't change per environment.
5. **No `/health` endpoint** — platform can't tell if the app is alive to restart it.
6. **Bound to `host="localhost"`** — unreachable from outside the container/network; cloud LBs can't reach it.
7. **Hardcoded `port=8000`** — ignores the `PORT` env var that Railway/Render/Cloud Run inject.
8. **`reload=True`** — dev hot-reload running in a production-style start; wastes resources and is unsafe.
9. **No graceful shutdown** — SIGTERM kills the process mid-request.

**Verified live** (`python app.py`):
```text
POST /ask?question=Hello   -> 200 {"answer":"..."}   # works on my machine
GET  /health               -> HTTP 404                # no health endpoint!
stdout log: [DEBUG] Using key: sk-hardcoded-fake-key-never-do-this   # secret leaked
```

### Exercise 1.3: Comparison table (`develop/app.py` vs `production/app.py`)
| Feature | Develop (basic) | Production (advanced) | Why important? |
|---------|-----------------|------------------------|----------------|
| Config | Hardcoded constants | `config.py` reads env vars | Same image runs in dev/staging/prod with no code change (12-Factor III). |
| Secrets | Hardcoded + printed | From env, never logged | Prevents credential leaks in Git/logs. |
| Binding | `localhost` | `0.0.0.0` | Reachable inside containers / behind a load balancer. |
| Port | Fixed `8000` | Reads `PORT` | Cloud platforms inject the port at runtime. |
| Health check | Missing (404) | `GET /health` → 200 | Liveness probe; platform restarts unhealthy containers. |
| Readiness | Missing | `GET /ready` → 200/503 | LB stops routing during startup/shutdown. |
| Logging | `print()` | JSON structured logs | Parseable in Datadog/Loki/CloudWatch. |
| Shutdown | Abrupt | Lifespan + SIGTERM handler + `timeout_graceful_shutdown` | In-flight requests finish before exit. |

**Verified live** (advanced on `:8001`):
```text
GET /health -> 200 {"status":"ok","uptime_seconds":3.2,"version":"1.0.0",...}
GET /ready  -> 200 {"ready":true}
POST /ask   -> 200 {"question":"Hello","answer":"...","model":"gpt-4o-mini"}
SIGTERM     -> "Graceful shutdown ... Application shutdown complete."
```

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)
1. **Base image:** `python:3.11` (the full distribution, ~1 GB).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Why `COPY requirements.txt` before the code?** Docker caches layers. Dependencies change rarely, code changes often. Copying + installing requirements first means a code-only change reuses the cached `pip install` layer → much faster rebuilds.
4. **CMD vs ENTRYPOINT:** `CMD` is the *default* command and is easily overridden by `docker run <image> <other>`. `ENTRYPOINT` defines the executable that always runs; `CMD` then supplies its default arguments. Use `ENTRYPOINT` for a fixed binary, `CMD` for overridable defaults.

### Exercise 2.3: Multi-stage build & image-size comparison
- **Stage 1 (`builder`):** installs build tools (`gcc`, `libpq-dev`) and compiles/installs all Python deps into `~/.local`. This image is never deployed.
- **Stage 2 (`runtime`):** starts from a clean `python:3.11-slim`, copies *only* the installed packages from the builder + the app code, runs as a non-root `appuser`, and adds a `HEALTHCHECK`. The compiler toolchain never reaches the final image → smaller + smaller attack surface.

**Measured on this machine** (`docker build` + `docker images`):
- Develop (single-stage, `python:3.11`): **1.67 GB**
- Production (multi-stage, `python:3.11-slim`, from `06-lab-complete`): **332 MB**
- Difference: **~80% smaller** (1670 MB → 332 MB), well under the 500 MB requirement.

### Exercise 2.4: Docker Compose architecture
`02-docker/production/docker-compose.yml` defines 4 services on an internal bridge network:
```
Client → Nginx (:80/:443, reverse proxy + LB) → agent (FastAPI, 2 replicas)
                                                    ├─ Redis  (session cache + rate limit)
                                                    └─ Qdrant (vector DB for RAG)
```
- Only **nginx** publishes ports; `agent`, `redis`, `qdrant` are internal-only (defense in depth).
- Services find each other by service name DNS (`redis:6379`, `qdrant:6333`).
- `depends_on: condition: service_healthy` makes the agent wait until Redis/Qdrant pass their healthchecks before starting.
- Named volumes (`redis_data`, `qdrant_data`) persist data across restarts.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Cloud deployment (Render)
- **Public URL:** https://ai-agent-production-n3l0.onrender.com
- **Platform:** Render — Docker web service (`plan: free`) + Render Key Value (Redis), region Singapore, via [render.yaml](render.yaml) Blueprint (`rootDir: 06-lab-complete`).
- **Verified live:**
```text
GET  /health -> 200 {"status":"ok","environment":"production","checks":{"llm":"openai","redis":"ok"}}
GET  /ready  -> 200 {"ready":true,"storage":"redis"}
POST /ask (no key) -> 401
```
- Railway alternative is also ready in [06-lab-complete/railway.toml](06-lab-complete/railway.toml).
- Screenshot: see `screenshots/`.

### Exercise 3.2: `render.yaml` vs `railway.toml` — what's different?
| | `railway.toml` | `render.yaml` |
|--|----------------|----------------|
| Format | TOML | YAML (Blueprint spec) |
| Build | `builder = "NIXPACKS"` (or `DOCKERFILE`) | `runtime: python` / `docker`; explicit `buildCommand` |
| Managed Redis | not declared in the file (add via dashboard/plugin) | declared as a `type: redis` service in the same blueprint |
| Secrets | `railway variables set ...` (CLI/dashboard) | `envVars` with `sync: false` (manual) or `generateValue: true` (auto-generated) |
| Scope | mostly a single service's deploy/health config | full infra-as-code: web service + redis + env in one file |

Railway's config is lighter (one service, port auto-injected); Render's blueprint describes the whole stack declaratively and can provision the Redis add-on alongside the web service.

### Exercise 3.3 (optional): GCP Cloud Run CI/CD
`cloudbuild.yaml` is a 4-step pipeline: **test** (pytest) → **build** Docker image (tagged with `$COMMIT_SHA`, `--cache-from latest`) → **push** to GCR → **deploy** to Cloud Run (`--min-instances=1` to avoid cold start, `--max-instances=10`, `--set-secrets` from Secret Manager). `service.yaml` is the declarative Knative service: autoscaling min/max, `containerConcurrency: 80`, liveness probe on `/health`, startup probe on `/ready`, secrets via `secretKeyRef`. Together they give automated build→deploy on push with no hardcoded secrets.

---

## Part 4: API Security

### Exercise 4.1: API key auth (`04-api-gateway/develop`)
- The key is checked in the `verify_api_key` FastAPI **dependency** (`Security(api_key_header)` reading header `X-API-Key`), injected into `/ask` via `Depends`.
- Missing key → **401**; present-but-wrong key → **403**.
- Rotating: change the `AGENT_API_KEY` env var and restart (no code change).

**Verified live** (`AGENT_API_KEY=secret-key-123`):
```text
no key      -> HTTP 401
wrong key   -> HTTP 403
correct key -> HTTP 200 {"question":"hi","answer":"..."}
```

### Exercise 4.2: JWT auth (`04-api-gateway/production/auth.py`)
Flow: `POST /auth/token` with username/password → server validates against `DEMO_USERS`, returns a signed HS256 JWT (`sub`, `role`, `iat`, `exp` = +60 min). Client sends `Authorization: Bearer <token>`; `verify_token` decodes + validates the signature/expiry and extracts `{username, role}` — **stateless**, no DB hit per request. Expired → 401, invalid/tampered → 403.

### Exercise 4.3: Rate limiting (`04-api-gateway/production/rate_limiter.py`)
- **Algorithm:** Sliding-window counter — a `deque` of timestamps per user; old timestamps outside the 60s window are popped on each check.
- **Limit:** user tier = **10 req/min**, admin tier = **100 req/min** (two `RateLimiter` instances).
- **Admin bypass:** in `/ask`, `limiter = rate_limiter_admin if role == "admin" else rate_limiter_user` — the JWT `role` claim selects the higher limit.

**Verified live** (student token, 10/min):
```text
req 1..9  -> 200   (plus 1 earlier call = 10 total)
req 10..13 -> 429   {"error":"Rate limit exceeded","limit":10,...}

ADMIN BYPASS (teacher token, 100/min) — same 13 requests:
200 200 200 200 200 200 200 200 200 200 200 200 200   # never throttled
invalid token -> HTTP 403
```

### Exercise 4.4: Cost guard
**Develop** (`cost_guard.py`, in-memory): per-user `UsageRecord` tracks tokens/cost per day, `check_budget()` raises **402** when a user hits the daily budget ($1/day) and **503** when the global budget ($10/day) is exhausted; warns at 80%. **Production** (`06-lab-complete/app/cost_guard.py`, Redis): spend per user per month in a Redis hash `usage:{YYYY-MM}:{user_id}`, TTL ~370 days for auto-reset. `/ask` estimates cost before and after the LLM call, raises **402** if `used + projected > MONTHLY_BUDGET_USD`, then records usage atomically.

**Verified live** (instance with `MONTHLY_BUDGET_USD=0.0000001`):
```text
POST /ask -> HTTP 402 {"detail":{"error":"Monthly budget exceeded","budget_usd":1e-07,...}}
```
Redis-backed = the budget is enforced consistently across all instances (in-memory would let each replica track its own count).

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks (`05-scaling-reliability/develop`)
`GET /health` (liveness) returns status + uptime + a memory check via `psutil`; `GET /ready` (readiness) returns 200 only when `_is_ready`, else 503. **Verified live:**
```text
GET /health -> 200 {"status":"ok","uptime_seconds":2.9,"checks":{"memory":{"status":"ok","used_percent":65.8}}}
GET /ready  -> 200 {"ready":true,"in_flight_requests":1}
```

### Exercise 5.2: Graceful shutdown
A SIGTERM handler logs the signal; the lifespan shutdown flips `_is_ready=False` and waits (up to 30s) for `_in_flight_requests` to drain before exiting; `uvicorn.run(..., timeout_graceful_shutdown=30)`. **Verified live** — sending SIGTERM (signal 15):
```text
Received signal 15 — uvicorn will handle graceful shutdown
🔄 Graceful shutdown initiated...
✅ Shutdown complete
Application shutdown complete.
```

### Exercise 5.3: Stateless design
Anti-pattern: `conversation_history = {}` in process memory — lost when a request lands on a different replica. Fix: store history/sessions in **Redis** (`save_session`/`load_session` with TTL), so any instance can serve any request.

### Exercise 5.4 & 5.5: Load balancing + `test_stateless.py`
Ran `docker compose up --scale agent=3` (3 agents + redis + nginx LB) and `python test_stateless.py`. **Verified live:**
```text
Session ID: dda00c4c-8006-4089-b195-3471bbbd7e28
Request 1: [instance-0f318d]   What is Docker?
Request 2: [instance-2aa0ce]   Why do we need containers?
Request 3: [instance-460647]   What is Kubernetes?
Request 4: [instance-0f318d]   How does load balancing work?
Request 5: [instance-2aa0ce]   What is Redis used for?
Instances used: {instance-460647, instance-2aa0ce, instance-0f318d}   # all 3 (round-robin)
--- Conversation History --- Total messages: 10   # full history preserved
✅ Session history preserved across all instances via Redis!
```
One conversation was served by **three different containers** yet kept full history — that's the stateless property that makes horizontal scaling work. nginx round-robins and retries on `error/timeout/http_503` (`proxy_next_upstream`).

---

## Part 6: Final Project (`06-lab-complete`)

Production-ready agent combining everything. **Verified end-to-end** with `docker compose up --scale agent=3` (3 agents + redis + nginx):

| Requirement | Result |
|-------------|--------|
| Multi-stage Dockerfile, image < 500 MB | **332 MB** ✅ |
| Config from env vars (`app/config.py`) | ✅ |
| API key auth | no key → 401, valid → 200 ✅ |
| Rate limiting 10/min (Redis sliding window) | 10×200 then 429 on #11 ✅ |
| Cost guard $10/month (Redis) | over budget → 402 ✅ |
| `/health` + `/ready` | 200 / 503 ✅ |
| Graceful shutdown (SIGTERM) | handler registered ✅ |
| Stateless (Redis history) | conversation across 3 instances intact ✅ |
| Structured JSON logging | ✅ |
| Load balancing (nginx) | round-robin across 3 instances ✅ |
| `check_production_ready.py` | **20/20 (100%)** ✅ |

**Bug fixed during verification:** `app/main.py` called `response.headers.pop()`, which doesn't exist on Starlette's `MutableHeaders` → every request returned 500. Changed to `del response.headers["server"]`. After the fix all endpoints return correctly.

**Remaining for full submission (needs your cloud account):** deploy to Railway/Render for a public URL + add screenshots. Configs (`railway.toml`, `render.yaml`) are ready.
