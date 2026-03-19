# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# SocialEntangler — Social Media Scheduler

Multi-platform social media scheduling SaaS. Architecture v2.8 (Celery + Redis Beat, MongoDB Atlas, Firebase Auth, workspace/teams).

**Active branch:** `architecture/v2` (based on `version-6`)

---

## Commands

### Backend (FastAPI + Celery)

```bash
cd backend
source venv/bin/activate          # Python 3.11 venv

# Run dev server
uvicorn server:app --reload --port 8001

# Run database migrations
python -m migrations.runner up        # Apply pending
python -m migrations.runner status    # Check status
python -m migrations.runner down      # Rollback last

# Run Celery worker (needs Redis running)
celery -A celery_app worker --loglevel=info --concurrency=4

# Run Celery Beat scheduler
celery -A celery_app beat --loglevel=info

# Inspect Celery
celery -A celery_app inspect active
celery -A celery_app inspect ping

# Health checks
curl http://localhost:8001/health
curl http://localhost:8001/ready
```

### Frontend (React/CRA)

```bash
cd frontend
npm install --legacy-peer-deps      # react-day-picker peer dep conflict
npm start                           # Dev server on :3000
npm run build                       # Production build
```

### Docker (Production)

```bash
# Start all services (api, worker, beat, nginx, redis)
docker-compose up -d

# View logs
docker-compose logs -f api
docker-compose logs -f worker

# Run migrations in production
docker-compose exec api python -m migrations.runner up

# Scale workers
docker-compose up -d --scale worker=4
```

---

## Architecture

### Request Flow

```
Browser → nginx (port 80)
       → /api/* → FastAPI (port 8001)
       → /       → React SPA (static files)
```

### Scheduling Flow

```
FastAPI saves post (status=scheduled) → MongoDB
→ Celery Beat (every 1 min) → redis queue
→ Celery worker picks up → publishes to social APIs
→ Updates post status (published/failed) + creates Notification
```

### Auth Flow

```
Google popup → Firebase JWT → GET /api/auth/me → MongoDB user lookup/create
→ setUser() in AuthContext → PrivateRoute allows access
```

---

## Key Files

| File | Purpose |
|------|---------|
| `backend/server.py` | Main FastAPI app — all endpoints (5300+ lines) |
| `backend/celery_app.py` | Celery app config + Beat schedule |
| `backend/celery_tasks.py` | Celery task definitions |
| `backend/migrations/` | Zero-downtime DB migrations (001–006 applied) |
| `backend/app/circuit_breaker.py` | Per-platform circuit breaker |
| `backend/app/media_validator.py` | FFmpeg-based media validation |
| `backend/app/dlq.py` | Dead Letter Queue for failed tasks |
| `backend/app/models/workspace.py` | Workspace/team model |
| `backend/app/social/*.py` | Platform OAuth + publish logic |
| `frontend/src/context/AuthContext.js` | Firebase auth state + backend sync |
| `frontend/src/pages/` | All page components |
| `frontend/src/lib/api.js` | All API helper functions |
| `docker-compose.yml` | Production Docker Compose |
| `nginx/nginx.conf` | nginx reverse proxy config |
| `ARCHITECTURE.md` | Full architecture reference |

---

## Database Collections

`users` · `posts` · `social_accounts` · `notifications` · `payment_transactions` · `workspaces` · `workspace_invites` · `api_keys` · `migrations_log` · `media_assets`

---

## Environment Variables (backend/.env)

```
MONGO_URL                 MongoDB Atlas connection string
DB_NAME                   Database name
REDIS_URL                 redis://localhost:6379/0
JWT_SECRET                HS256 fallback signing key
FIREBASE_STORAGE_BUCKET   Optional — uses local disk if empty
GOOGLE_CLIENT_ID/SECRET   YouTube OAuth
FACEBOOK_APP_ID/SECRET    Facebook + Instagram OAuth
TWITTER_CLIENT_ID/SECRET  Twitter OAuth
LINKEDIN_CLIENT_ID/SECRET LinkedIn OAuth
RESEND_API_KEY            Email (Resend)
STRIPE_API_KEY            Stripe payments
RAZORPAY_KEY_ID/SECRET    Razorpay (INR)
FRONTEND_URL              http://localhost:3000 (dev)
SERVICE_URL               Backend public URL
ENV                       "production" → JSON logs
```

---

## Platform Publishing Notes

- **Instagram/Facebook videos**: Create container → poll status (30×5s) → publish. Uses `thumbnail_url` for VIDEO/REELS display (not `media_url`).
- **YouTube**: Resumable upload protocol. Auto-refreshes OAuth token on 401.
- **Retry logic**: 3 attempts, 5 min apart. Tracked in `retry_count` + `status_history`.
- **Per-platform independence**: Each platform publishes independently — one failure doesn't block others.

---

## Workspace / Teams

- Every user auto-gets a personal workspace on first login
- `GET /api/workspace` — fetch/create workspace
- `POST /api/workspace/invite` — invite by email
- `GET /api/workspace/activity` — team activity feed
- Posts are workspace-scoped (teammates see each other's posts)
- Role-based access: `owner > admin > editor > viewer`

---

## GDPR / Compliance

- `GET /api/gdpr/export` — download all user data as JSON
- `DELETE /api/gdpr/delete-account` — permanent erasure (GDPR Art. 17)
- `GET /api/gdpr/status` — data summary

---

## API Keys (Developer API)

- `GET/POST /api/api-keys` — list/create API keys
- `DELETE /api/api-keys/{id}` — revoke
- Keys use `se_live_` prefix, SHA-256 hashed in DB, shown only once on creation
