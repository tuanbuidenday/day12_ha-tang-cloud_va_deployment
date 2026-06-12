# Day 12 — Solution / Bài Nộp

> **Sinh viên:** Bùi Văn Tuân — **MSSV:** 2A202601006
> **Môn:** AICB-P1 · VinUniversity 2026 — Day 12: Deployment
> **Repo:** https://github.com/tuanbuidenday/day12_ha-tang-cloud_va_deployment

Tài liệu này tổng hợp toàn bộ lời giải và chỉ rõ **mỗi yêu cầu được đáp ứng ở đâu**, kèm **bằng chứng đã chạy thật** (Docker stack 3 instances + chạy từng app FastAPI). Mọi kết quả test bên dưới đều là output thực tế trên máy.

---

## 1. Các file nộp (theo Delivery Checklist)

| Yêu cầu | File | Trạng thái |
|---------|------|-----------|
| Mission Answers (40đ) | [MISSION_ANSWERS.md](MISSION_ANSWERS.md) | ✅ Trả lời Part 1–6, có output thật |
| Full source code (60đ) | [06-lab-complete/](06-lab-complete/) | ✅ Đầy đủ, chạy không lỗi |
| Service domain link | [DEPLOYMENT.md](DEPLOYMENT.md) | ✅ (Public URL điền sau khi deploy) |
| Solution tổng hợp | [SOLUTION.md](SOLUTION.md) | ✅ (file này) |

---

## 2. Lời giải theo từng Part

Chi tiết đầy đủ + bảng so sánh + output nằm trong [MISSION_ANSWERS.md](MISSION_ANSWERS.md). Tóm tắt:

- **Part 1 — Localhost vs Production:** tìm 9 anti-patterns trong [develop/app.py](01-localhost-vs-production/develop/app.py); so sánh với bản 12-Factor [production/app.py](01-localhost-vs-production/production/app.py). *Verified:* basic không có `/health` (404) và leak key ra log; advanced `/health`+`/ready`+`/ask` đều 200.
- **Part 2 — Docker:** giải thích base image, layer cache, CMD vs ENTRYPOINT, multi-stage. *Verified image size:* develop **1.67 GB** → production **332 MB** (~80% nhỏ hơn, < 500 MB).
- **Part 3 — Cloud Deployment:** so sánh `railway.toml` vs `render.yaml`, phân tích CI/CD Cloud Run (`cloudbuild.yaml` + `service.yaml`).
- **Part 4 — API Security:** API key (401/403/200), JWT flow, rate limit sliding-window, admin bypass, cost guard. *Verified:* student 429 ở request #10, teacher (admin) 13 request đều 200, budget vượt → 402.
- **Part 5 — Scaling & Reliability:** health/readiness, graceful shutdown (SIGTERM/signal 15), stateless Redis. *Verified:* `test_stateless.py` — 1 hội thoại được phục vụ bởi **3 instance khác nhau**, history 10 message còn nguyên trong Redis.

---

## 3. Final Project — ánh xạ Grading Rubric (100đ)

Toàn bộ ở [06-lab-complete/](06-lab-complete/). Mỗi tiêu chí + nơi cài đặt + bằng chứng:

| Tiêu chí | Điểm | Cài đặt ở đâu | Bằng chứng (đã chạy thật) |
|----------|------|---------------|---------------------------|
| **Functionality** | 20 | [app/main.py](06-lab-complete/app/main.py) — `/ask`, conversation history, `/sessions/{id}/history` | `POST /ask` → 200 + answer + usage; history trả về đủ message |
| **Docker** | 15 | [Dockerfile](06-lab-complete/Dockerfile) multi-stage, non-root, HEALTHCHECK | Image **332 MB** < 500 MB |
| **Security** | 20 | [auth.py](06-lab-complete/app/auth.py), [rate_limiter.py](06-lab-complete/app/rate_limiter.py), [cost_guard.py](06-lab-complete/app/cost_guard.py) | no key → 401; >10/min → 429; vượt budget → 402 |
| **Reliability** | 20 | [main.py](06-lab-complete/app/main.py) — `/health`, `/ready`, SIGTERM handler, JSON logging | `/health` 200, `/ready` 200/503, shutdown handler có |
| **Scalability** | 15 | [conversation_store.py](06-lab-complete/app/conversation_store.py) (Redis), [nginx.conf](06-lab-complete/nginx.conf) LB | hội thoại liền mạch qua 3 instance; nginx round-robin |
| **Deployment** | 10 | [render.yaml](render.yaml) (root, `rootDir: 06-lab-complete`), [railway.toml](06-lab-complete/railway.toml) | Public URL → xem [DEPLOYMENT.md](DEPLOYMENT.md) |

**Validator tự động:** `python 06-lab-complete/check_production_ready.py` → **20/20 (100%)**.

---

## 4. Cách chạy & kiểm tra (local)

```bash
cd 06-lab-complete
docker compose up --build --scale agent=3      # 3 agent + redis + nginx (LB tại :8080)

KEY=dev-key-change-me-in-production
curl http://localhost:8080/health                                   # 200
curl http://localhost:8080/ready                                    # 200
curl -X POST http://localhost:8080/ask                              # 401 (thiếu key)
curl -X POST http://localhost:8080/ask -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'                        # 200

# Rate limit: gọi 13 lần cùng user → 10×200 rồi 429
for i in $(seq 1 13); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8080/ask \
    -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"user_id":"rate","question":"t"}'; done

python check_production_ready.py               # 20/20
```

---

## 5. Bug đã sửa trong quá trình verify

[app/main.py](06-lab-complete/app/main.py): `response.headers.pop()` không tồn tại trên `MutableHeaders` của Starlette → mọi request trả 500. Đã đổi thành `del response.headers["server"]`. Sau khi sửa, toàn bộ endpoint chạy đúng.

---

## 6. Trạng thái Deployment

Cấu hình sẵn sàng: [render.yaml](render.yaml) ở **gốc repo** với `rootDir: 06-lab-complete`, tự tạo Redis (`type: keyvalue`) và web service `plan: free` (không cần thẻ). Public URL sẽ được điền vào [DEPLOYMENT.md](DEPLOYMENT.md) sau khi deploy.

- [x] Code đầy đủ, chạy không lỗi (validator 20/20)
- [x] Multi-stage Dockerfile (332 MB < 500 MB)
- [x] Auth + rate limit + cost guard
- [x] Health + readiness + graceful shutdown
- [x] Stateless (Redis) + load balancing (nginx)
- [x] Không hardcode secret
- [ ] Public URL (cần deploy bằng tài khoản Render/Railway)
- [ ] Screenshots (`screenshots/`)
