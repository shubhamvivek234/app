# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# SocialEntangler — Social Media Scheduler

A full-stack social media scheduling platform. Users create, schedule, and publish posts to 10+ platforms (Instagram, Facebook, YouTube, Twitter/X, LinkedIn, TikTok, Reddit, Pinterest, Bluesky, Snapchat, Threads). Includes AI content generation, calendar view, subscription billing, team collaboration, analytics, and an approval workflow.

**Current branch:** `architecture/v2` — implements Architecture Blueprint v2.8 + Addendum (Celery, migrations, health checks, workspace model, rate limiting, per-platform publishing, etc.)

---

## Commands

### Backend
```bash
cd backend
source venv/bin/activate

# Run dev server
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Run migrations (always run after pulling new changes)
python -m migrations.runner up       # Apply pending migrations
python -m migrations.runner status   # Show migration status
python -m migrations.runner down     # Roll back last migration

# Celery (only needed in production or when testing scheduled publishing)
celery -A celery_app worker --loglevel=info --concurrency=4
celery -A celery_app beat --loglevel=info
celery -A celery_app inspect active

# Lint / format
black .
flake8 .

# Tests
pytest
pytest -v tests/test_auth.py
pytest --cov
```

### Frontend
```bash
cd frontend

# NOTE: Use npm — yarn is NOT installed
npm install --legacy-peer-deps   # --legacy-peer-deps required for react-day-picker conflict
npm start                         # Dev server on port 3000 (proxies API to :8001)
npm run build                     # Production build
npm test
```

### Docker Compose (Production)
```bash
docker-compose up -d              # Start all services (api, worker, beat, redis, nginx)
docker-compose logs -f api
docker-compose exec api python -m migrations.runner up
curl http://localhost:8001/health
curl http://localhost:8001/ready
```

---

## Architecture Overview

See **`ARCHITECTURE.md`** for the full end-to-end reference. Key points for daily development:

### Backend (`backend/server.py`)
Single monolithic file (~5,400+ lines). All routes are defined here. OAuth logic stays in `backend/app/social/` — never inline it.

**Core dependencies (v2.8):**
- FastAPI + Uvicorn
- Motor (async MongoDB driver) with explicit connection pooling
- Celery + Redis Beat (replaces APScheduler for scheduled publishing)
- Firebase Admin SDK (auth verification + Cloud Storage)
- structlog (structured JSON logging with trace_id correlation)
- slowapi (rate limiting)

**Request auth flow:**
1. `Authorization: Bearer <token>` header parsed by `get_current_user()` dependency
2. Token verified as Firebase ID token (primary) — no password needed for Google users
3. Falls back to local HS256 JWT (legacy `/auth/callback` flow)
4. MongoDB user looked up / created / migrated; subscription expiry auto-checked

**Scheduler flow (Celery):**
- `celery_app.py` — Celery app config (Redis broker, Beat schedule)
- `celery_tasks.py` — task definitions
- Beat runs `process_scheduled_posts` every 1 minute; workers execute it
- `task_acks_late=True` + `task_reject_on_worker_lost=True` — no lost tasks on crash

**Per-platform independent publishing (Stage 1.6):**
Each social account publishes independently. `platform_results` in the post document tracks per-platform success/failure. A "partial" publish (some succeed, some fail) counts as published. The post only retries failed platforms.

**Idempotency guard:**
Scheduler does an atomic `update_one({status:"scheduled"} → {status:"processing"})` before working on a post. If `modified_count == 0`, another worker already claimed it — skip.

### Social OAuth Modules (`backend/app/social/`)
| Module | Class | Notes |
|---|---|---|
| `google.py` | `GoogleAuth` | YouTube OAuth; set `MOCK_GOOGLE_AUTH=true` in dev |
| `twitter.py` | `TwitterAuth` | Twitter/X OAuth v2 |
| `linkedin.py` | `LinkedInAuth` | LinkedIn OAuth |
| `facebook.py` | `FacebookAuth` | Facebook OAuth + Graph API |
| `instagram.py` | `InstagramAuth` | Falls back to `FACEBOOK_APP_*` if `INSTAGRAM_*` not set |
| `tiktok.py` | `TikTokAuth` | TikTok OAuth |
| `reddit.py` | `RedditAuth` | Reddit OAuth |
| `pinterest.py` | `PinterestAuth` | Pinterest OAuth |
| `bluesky.py` | `BlueskyAuth` | Bluesky API |
| `snapchat.py` | `SnapchatAuth` | Snapchat OAuth |
| `threads.py` | `ThreadsAuth` | Threads/Meta API |

### Database Migrations (`backend/migrations/`)
Every schema change goes through a migration. **Never modify the schema without a migration.**

```
migrations/
├── runner.py            ← CLI: python -m migrations.runner up/down/status
├── 001_add_timezone_to_users.py
├── 002_add_indexes.py
├── 003_add_platform_results_to_posts.py
├── 004_add_workspace_collection.py
└── ...
```

Each migration file has `up(db)` and `down(db)` async functions. Applied migrations are tracked in the `migrations_log` MongoDB collection.

**Zero-downtime protocol:** add fields with defaults first → deploy code → backfill → remove old fields.

### Frontend (`frontend/src/`)
React 19 + Craco (custom webpack). Path alias `@/*` → `src/*`.

- All API calls: `src/lib/api.js` — never call axios directly in components
- Auth state: `useAuth()` from `AuthContext` — exposes `{ user, firebaseUser, loading, token, login, signup, loginWithGoogle, logout, refreshUser }`
- Protected routes: `<PrivateRoute>` / `<PublicRoute>` in `App.js`
- UI components: `src/components/ui/` (shadcn/Radix) — don't re-implement
- Login: `Login.js` randomly shows one of 4 designs (`LoginV1–V4.js`). Same pattern for Signup.

### Workspace / Teams (`Stage 5.9`)
- Model in `backend/app/models/workspace.py`
- API endpoints: `GET/POST /api/workspace`, `POST /api/workspace/invite`, `POST /api/workspace/invite/{token}/accept`, `DELETE /api/workspace/members/{id}`
- Roles: `owner > admin > editor > viewer` — permissions in `ROLE_PERMISSIONS` dict
- Every new user gets an auto-created personal workspace

---

## Environment Variables

### Backend (`backend/.env`)
```
MONGO_URL                 MongoDB connection string
DB_NAME                   Database name
REDIS_URL                 redis://localhost:6379/0
JWT_SECRET                HS256 signing key
JWT_ALGORITHM             HS256
FRONTEND_URL              http://localhost:3000
SERVICE_URL               Backend public URL (for media URL construction)
ENV                       "production" → JSON logs; else colored console
FIREBASE_STORAGE_BUCKET   Firebase bucket (optional; local disk fallback if empty)
RESEND_API_KEY            Email service
SENDER_EMAIL              From address for emails
STRIPE_API_KEY            Stripe payments
RAZORPAY_KEY_ID/SECRET    Razorpay payments
MOCK_GOOGLE_AUTH          Set "true" in dev to skip real Google OAuth
# OAuth per platform: {PLATFORM}_CLIENT_ID, {PLATFORM}_CLIENT_SECRET, {PLATFORM}_REDIRECT_URI
GOOGLE_CLIENT_ID/SECRET + YOUTUBE_REDIRECT_URI
TWITTER_CLIENT_ID/SECRET/REDIRECT_URI
LINKEDIN_CLIENT_ID/SECRET/REDIRECT_URI
FACEBOOK_APP_ID/SECRET/REDIRECT_URI
INSTAGRAM_APP_ID/SECRET/REDIRECT_URI
TIKTOK_CLIENT_KEY/SECRET/REDIRECT_URI
```

### Frontend (`frontend/.env`)
```
REACT_APP_BACKEND_URL=http://localhost:8001
```

---

## Health & Observability

```bash
# Liveness + readiness probes
curl http://localhost:8001/health   # → {"status":"ok"}
curl http://localhost:8001/ready    # → {"status":"ready","checks":{"mongodb":"ok","redis":"ok"}}
```

Every HTTP request gets a `trace_id` (UUID) logged with `structlog`. The `X-Trace-ID` header is returned on every response. Celery tasks carry `trace_id` in kwargs for cross-service correlation.

---

## Subscription & Feature Gating

- Scheduling posts (`scheduled_time`) requires `subscription_status == "active"`
- Free users can only create drafts
- Subscription auto-expires: `get_current_user()` checks `end_date < now` on every request
- Pricing: Monthly ₹500 / Yearly ₹3,000 (INR, Razorpay primary; Stripe for international)

---

## Payment Flows

- **Stripe:** Webhook at `POST /api/webhook/stripe`; status at `GET /api/payments/status/{session_id}`
- **Razorpay:** Creates order → redirects to `/razorpay-checkout?order_id=...`

After successful payment: `subscription_status → "active"`, `subscription_end_date` set on user doc.

---

## Critical Don'ts

- **Never destructure `setUser` or `setToken` from `useAuth()`** — not exported. Context exposes: `user, firebaseUser, loading, token, login, signup, loginWithGoogle, logout, refreshUser`
- **Never inline OAuth logic in `server.py`** — all OAuth code belongs in `backend/app/social/`
- **Never call APIs directly in React components** — use `src/lib/api.js`
- **Never hardcode backend URL** — use `process.env.REACT_APP_BACKEND_URL`
- **Never hardcode OAuth redirect URIs** — always read from env vars
- **Never modify the DB schema without a migration** — create a new file in `backend/migrations/`
- **Never re-implement shadcn components** — use `src/components/ui/`
- **Never add worktree `.env` files to git** — they contain secrets
- **Worktrees need their own `frontend/.env`** — copy from `frontend/.env` or API calls will silently fail

---

## Useful Files

| File | Purpose |
|---|---|
| `ARCHITECTURE.md` | Full architecture reference: auth, DB schema, scheduling, retry logic, cost model |
| `backend/migrations/runner.py` | Migration CLI |
| `backend/celery_app.py` | Celery + Beat configuration |
| `backend/celery_tasks.py` | Scheduled task definitions |
| `backend/app/models/workspace.py` | Workspace / team model |
| `backend/app/media_validator.py` | File size + format validation |
| `backend/app/dlq.py` | Dead Letter Queue for failed tasks |
| `docker-compose.yml` | Production container layout |
| `frontend/craco.config.js` | Webpack / path alias config |
| `frontend/src/lib/api.js` | All frontend API calls |
| `frontend/src/context/AuthContext.js` | Auth state management |
