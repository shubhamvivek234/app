# SocialEntangler — Architecture Blueprint v2.8 + Addendum

> Last updated: March 2026. Incorporates v2.8 Addendum (Cost Optimisation + 7 Missing Components + 3 Sequencing Fixes).

---

## 1. TECH STACK

```
Frontend   : React (CRA → Vite in Stage 3.9), TailwindCSS, React Router, Axios, Firebase JS SDK
Backend    : FastAPI (Python 3.11), Celery + Redis Beat, Motor (async MongoDB), Firebase Admin SDK
Database   : MongoDB Atlas (M0 dev → M10 launch → M20 growth)
Queue      : Redis 7 (AOF persistence, noeviction policy for job queue)
Auth       : Firebase Authentication (Google OAuth + Email/Password)
File Store : Firebase Storage (launch) → Cloudflare R2 (growth, zero egress)
Email      : Resend (free tier → pay-as-you-go)
Payments   : Razorpay (INR primary) + Stripe (international)
CDN        : Cloudflare Free (launch) → Pro (growth)
Monitoring : Sentry free (launch) + Grafana Cloud free (launch)
Container  : Docker Compose on single VPS (launch) → Cloud Run / ECS Fargate (scale)
```

---

## 2. INFRASTRUCTURE COST MODEL (Revised — Addendum A.1)

| Stage | Users | Infrastructure | Est. Monthly Cost |
|-------|-------|---------------|-------------------|
| Dev | 0 | Atlas M0 free + Upstash Redis free + Cloudflare free | $5–10 |
| Launch | 0–5K | 1× VPS 4vCPU/8GB (Docker Compose) + Atlas M10 ($57) + Cloudflare free | $80–130 |
| Growth | 5K–15K | 2× VPS + Atlas M20 ($140) + managed Redis ($30) + Cloudflare Pro ($20) | $250–400 |
| Scale | 15K–30K | Cloud Run/Fargate + Atlas M30 ($350) + managed Redis ($50–80) | $700–1,100 |
| Enterprise | 30K+ | Auto-scaling + Redis Cluster + Atlas M40+ | $1,500+ |

**Key cost decisions (Addendum A.2):**
- Use VPS + Docker Compose until 10K–15K users (Kubernetes costs $70–75/month control plane minimum)
- Upstash Redis free tier for dev; self-hosted Redis on VPS at launch ($0 extra)
- Firebase Storage at launch; migrate to Cloudflare R2 at Growth stage (saves 50–70% on egress)
- Cloudflare free tier is sufficient at launch (CDN, SSL, DDoS protection)
- Spot/preemptible instances for Celery workers at Scale stage (60–80% cheaper; workers are stateless + idempotent)
- All services must be in the **same region** (see Phase 0.5 below)

---

## 3. AUTHENTICATION FLOW

### Google Login (Primary)
```
1. User clicks "Continue with Google"
2. Firebase signInWithPopup(auth, googleProvider) — popup opens
3. Google OAuth completes → Firebase User object returned
4. onAuthStateChanged fires in AuthContext:
   a. setLoading(true)  ← CRITICAL: prevents PrivateRoute race condition
   b. Gets Firebase ID token (short-lived JWT, RS256)
   c. Stores token in localStorage + sets Axios Authorization header
   d. Calls GET /api/auth/me (backend) with Bearer token
5. Backend get_current_user():
   a. Verifies Firebase ID token via Google public keys (no service account needed)
   b. Looks up user in MongoDB by Firebase UID
   c. If not found by UID: checks by email (legacy migration), or creates new user
   d. Checks subscription expiry; auto-expires if end_date < now
   e. Returns User object
6. setUser(response.data) → AuthContext user is set
7. setLoading(false) → PrivateRoute re-evaluates
8. PublicRoute redirects to /dashboard or /onboarding based on user state
```

### JWT Fallback (legacy backend OAuth)
If Firebase token verification fails, backend tries HS256 JWT. Used by legacy `/auth/callback?token=...` flow.

---

## 4. DATABASE SCHEMA (MongoDB Collections)

### `users`
```
user_id              : str      — Firebase UID (primary key)
email                : str      — unique
name                 : str
picture              : str      — profile photo URL
email_verified       : bool
timezone             : str      — IANA timezone (e.g. "Asia/Kolkata") [Addendum B.6]
created_at           : datetime (ISO string in DB)
subscription_status  : str      — "free" | "active" | "expired"
subscription_plan    : str      — e.g. "starter", "pro", "agency"
subscription_start_date : datetime
subscription_end_date   : datetime
user_type            : str      — "founder" | "creator" | "agency" | "enterprise" etc.
onboarding_completed : bool
has_password         : bool     — false for Google-only accounts
```

### `posts`
```
id                   : str      — UUID
user_id              : str      — FK to users
content              : str      — caption / post text
post_type            : str      — "text" | "image" | "video"
platforms            : [str]    — ["instagram", "facebook", ...]
accounts             : [str]    — list of social_account IDs
media_urls           : [str]    — uploaded file CDN URLs
video_url            : str
cover_image_url      : str      — video thumbnail
youtube_title        : str
youtube_privacy      : str      — "public" | "private" | "unlisted"
scheduled_time       : datetime — always stored in UTC
status               : str      — "draft" | "scheduled" | "published" | "failed" |
                                   "pending_review" | "expired_approval"
retry_count          : int      — 0–3
created_at           : datetime
published_at         : datetime
ai_generated         : bool
instagram_post_format     : str  — "Post" | "Reel" | "Story"
instagram_first_comment   : str
tiktok_privacy            : str
tiktok_allow_duet         : bool
thread_tweets             : [{}] — Twitter thread items
linkedin_document_url     : str
```

### `social_accounts`
```
id                   : str      — UUID
user_id              : str
platform             : str      — "instagram" | "facebook" | "youtube" | "twitter" | "linkedin" etc.
platform_user_id     : str
platform_username    : str
access_token         : str      — OAuth access token
refresh_token        : str      — OAuth refresh token
token_expiry         : datetime
is_active            : bool
account_type         : str      — "standalone" | "facebook_linked" (Instagram)
picture_url          : str
connected_at         : datetime
```

### `notifications`
```
id, user_id, post_id, type ("success"|"error"), message, is_read, created_at
```

### `payment_transactions`
```
id, user_id, session_id, payment_id, amount, currency, plan, payment_method, payment_status, metadata, created_at, updated_at
```

### `migrations_log`
```
migration_name, direction ("up"|"down"), applied_at, duration_ms, status ("success"|"failed"|"rolled_back"), error
```

**Compound indexes (Migration 002):**
- `posts`: `(user_id, status, scheduled_time)` — scheduler query
- `posts`: `(user_id, created_at DESC)` — feed queries
- `notifications`: `(user_id, is_read, created_at DESC)` — unread count
- `social_accounts`: `(user_id, platform)` — account lookup

---

## 5. FILE UPLOAD FLOW

### Upload to Firebase Storage (primary)
```
1. POST /api/upload (multipart/form-data, Bearer token required)
2. Backpressure check (Addendum B.7):
   - Per-user limit: Starter=3, Pro=5, Agency=10 concurrent uploads
   - Global queue limit: 200 pending — return HTTP 503 if exceeded
   - Return HTTP 429 + Retry-After: 30 if user limit exceeded
3. If FIREBASE_STORAGE_BUCKET env var set:
   - Generate unique filename: {UUID}.{ext}
   - Upload to Firebase Storage at path: uploads/{filename}
   - blob.make_public() → get public CDN URL
   - Return: { url: "https://storage.googleapis.com/...", ... }
4. Fallback (no Firebase bucket):
   - Save to backend/uploads/{filename} on local disk
   - Return: { url: "/uploads/{filename}", ... }
5. Decrement user upload counter on completion
```

### URL resolution at publish time
- URL starts with `https://` → use as-is (Firebase CDN)
- URL starts with `http://localhost` → extract local file path
- URL is a relative path → construct: `{SERVICE_URL}{path}`

### File cleanup
- Files are **deleted** after a post is published (success) or permanently failed (retry_count ≥ 3)
- Firebase Storage blobs and local files are both cleaned up
- The post record keeps the URL string (the platform has its own copy)

---

## 6. POST SCHEDULING FLOW

### Creating a scheduled post
```
1. POST /api/posts with scheduled_time (ISO UTC string)
2. Validation: subscription_status must be "active" (free users can only draft)
3. Saved to MongoDB: status="scheduled", retry_count=0
4. Celery Beat picks it up in the next 1-minute cycle
```

### The Scheduler (Celery + Redis Beat — replaces APScheduler)
```
Architecture: Celery Beat generates tasks → Redis queue → Celery workers consume
Beat schedule:
  - process_scheduled_posts_task  → every 1 minute (soft limit: 50s, hard: 58s)
  - expire_pending_review_task    → every 5 minutes

Reliability settings:
  - task_acks_late=True           → acknowledge AFTER completion (re-queue on crash)
  - task_reject_on_worker_lost=True
  - worker_prefetch_multiplier=1  → one task at a time per thread
  - worker_max_tasks_per_child=100 → restart worker after 100 tasks (prevent memory leaks)
```

### process_scheduled_posts (every minute)
```
1. Query: status="scheduled" AND scheduled_time <= now (up to 100 posts)
2. For each post:
   a. Fetch social_account (access_token, platform_user_id)
   b. Resolve media URL to public URL
   c. For YouTube/LinkedIn: download media to local temp file
   d. Call platform publish function
   e. Handle result (see retry logic below)
```

---

## 7. PLATFORM PUBLISHING + RETRY LOGIC

### Instagram
```
1. POST /{ig_user_id}/media → create container (image_url or video_url + media_type=REELS)
2. For VIDEO: poll status every 5s, up to 30 attempts (2.5 min) until FINISHED
3. POST /{ig_user_id}/media_publish { creation_id } → get media_id (confirmation)
```

### Facebook
```
Images: POST /{page_id}/photos { message, url }
Videos: POST /{page_id}/videos { description, file_url } + same polling
```

### YouTube
```
1. POST /upload/youtube/v3/videos?uploadType=resumable → get upload URL
2. PUT {upload_url} with raw video bytes → get video_id (confirmation)
3. Upload thumbnail (non-blocking)
4. Token auto-refresh: on AuthError + refresh_token → refresh + retry once
```

### Retry logic
```
Max retries: 3 attempts
On failure:
  - retry_count < 3 → status="scheduled", scheduled_time = now + 5 minutes
  - retry_count >= 3 → status="failed", create error Notification, clean up files
Timeline: T+0 (fail) → T+5min retry → T+10min retry → T+15min → FAILED
```

### Post status lifecycle
```
draft → scheduled (if scheduled_time set + subscription active)
      → published (on success)
      → failed (after 3 retries)
      → pending_review → scheduled/published
      → expired_approval (if pending_review past scheduled_time)
```

---

## 8. HEALTH CHECKS (Addendum B.1)

```
GET /health  → liveness probe: process alive? Returns 200 + {"status":"ok"}
GET /ready   → readiness probe: MongoDB ping + Redis ping
               Returns 200 {"status":"ready"} or 503 {"status":"not_ready"}

Celery Beat: writes beat_tick_at to Redis every cycle
             Unhealthy if beat_tick_at is > 90 seconds old

Docker Compose healthcheck: /health endpoint, 15s interval, 5s timeout
Kubernetes (Scale stage): livenessProbe on /health, readinessProbe on /ready
```

---

## 9. CONNECTION POOLING (Addendum B.3)

```
MongoDB (Motor):
  API pods:       maxPoolSize=25, minPoolSize=2
  Celery workers: maxPoolSize=10
  Celery Beat:    maxPoolSize=5
  All:            serverSelectionTimeoutMS=5000, connectTimeoutMS=5000

Redis (redis-py):
  API:     max_connections=20
  Workers: max_connections=10
  Pool:    ConnectionPool (not per-request connections)
```

---

## 10. STRUCTURED LOGGING (Addendum B.4)

```
Library: structlog
Format:  JSON in production, colored console in dev (ENV env var)
Fields per log line:
  - trace_id   (UUID, generated per request by add_correlation_id middleware)
  - user_id    (if authenticated)
  - post_id    (if post-related)
  - platform   (if platform-related)
  - timestamp  (ISO UTC)
  - level
  - message

Middleware: X-Trace-ID header on every response
Celery: trace_id passed in task kwargs, bound to structlog context
```

---

## 11. TIMEZONE HANDLING (Addendum B.6)

```
Storage: All scheduled_time stored in UTC
User field: timezone (IANA string, e.g. "Asia/Kolkata"), default "UTC"
Conversion: Server-side ONLY using Python's zoneinfo module (stdlib 3.9+)
Display: Frontend shows scheduled times in user's timezone + UTC tooltip
Recurring posts: Server recalculates scheduled_times when DST boundaries are crossed
```

---

## 12. UPLOAD BACKPRESSURE (Addendum B.7)

```
Per-user concurrent upload limits:
  free/starter: 2–3, pro: 5, agency: 10, enterprise: 20
  Implementation: Redis INCR/DECR counter per user (INCR on start, DECR on completion)
  Response on limit exceeded: HTTP 429 + Retry-After: 30

Global queue protection:
  If media_processing queue depth > 200 pending → HTTP 503 + Retry-After: 120
  Message: "High volume of uploads — try again in 2 minutes"

Frontend: auto-retry after Retry-After period, show user-friendly message
```

---

## 13. DATABASE MIGRATION STRATEGY (Addendum C.5)

```
Location: backend/migrations/
Naming:   {NNN}_{description}.py (e.g. 001_add_timezone_to_users.py)
Tracking: migrations_log collection in MongoDB
Commands:
  python -m migrations.runner up      # Apply pending migrations
  python -m migrations.runner down    # Rollback last migration
  python -m migrations.runner status  # Show status

Zero-downtime protocol:
  1. Add new fields with defaults (additive migration)
  2. Deploy code that writes to both old + new fields
  3. Backfill existing documents
  4. Deploy code reading only from new fields
  5. Cleanup migration removes old fields

Applied migrations:
  001_add_timezone_to_users    — adds timezone="UTC" to all users
  002_add_indexes              — compound indexes for query performance
```

---

## 14. ONBOARDING + SUBSCRIPTION FLOW

```
New user (first login):
  onboarding_completed=false → /onboarding → /onboarding/connect → /onboarding/pricing
  → Razorpay/Stripe payment → subscription_status="active" → /dashboard

Returning user: /dashboard directly

Free user (onboarding complete): → /onboarding/pricing (subscription gate)

Expired subscription: → /subscription-expired page

Backend enforcement:
  - POST /posts with scheduled_time → requires subscription_status="active"
  - get_current_user() auto-expires subscriptions past end_date
```

---

## 15. IMPLEMENTATION PHASES (v1.1 — Revised)

| Stage | Focus | Duration (1 eng) | Est. Cost at End |
|-------|-------|-----------------|------------------|
| 0 | Pre-Launch Foundations | 1.5 weeks | $5–10 |
| 1 | Core Infrastructure (Celery, health, pooling) | 7–9 weeks | $70–90 |
| 2 | Media Pipeline + Reliability | 8–9 weeks | $75–100 |
| 3 | Security Hardening | 7–9 weeks | $100–130 |
| 3.9 | Vite Migration (moved from 1.8) | 1 week | same |
| 4 | Observability + Redis HA | 3–4 weeks | $130–170 |
| 5 | Platform Quality + Workspace Model (moved from 3.8) | 7–8 weeks | $170–250 |
| 6 | Product Features + Teams | 4–5 weeks | $250–350 |
| 7 | Infrastructure Hardening | 4–5 weeks | $300–400 |
| 8–10 | Compliance + Scale + Operations | 12–15 weeks | $400–1,100 |

**New phases added in v1.1:**
- Phase 0.5: Same-region co-location (must be first; prevents $50–200/month cross-region egress)
- Phase 0.7: Database migration tooling ✅ (implemented)
- Phase 1.2: Health checks + graceful shutdown ✅ (implemented)
- Phase 1.3: Connection pooling + correlation IDs ✅ (implemented)
- Phase 2.8: Upload backpressure ✅ (implemented)
- Phase 4.6: Redis high availability (at Growth stage)
- Phase 5.2: User timezone support ✅ (implemented)

**Sequencing fixes:**
- Phase 1.8 (Vite) moved to Phase 3.9 (after backend stable)
- Phase 3.8 (Workspace model) moved to Phase 5.9 (before team features, not 3 stages early)

---

## 16. RUNNING THE PROJECT

### Development (local)
```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload --port 8001

# Run migrations
python -m migrations.runner up

# Frontend
cd frontend
npm install --legacy-peer-deps
npm start
```

### Production (Docker Compose)
```bash
# Copy .env and serviceAccountKey.json to backend/
docker-compose up -d

# Check health
curl http://localhost:8001/health
curl http://localhost:8001/ready

# View logs
docker-compose logs -f api
docker-compose logs -f worker

# Run migrations in production
docker-compose exec api python -m migrations.runner up
```

### Celery (if running without Docker)
```bash
# Worker
celery -A celery_app worker --loglevel=info --concurrency=4

# Beat scheduler
celery -A celery_app beat --loglevel=info

# Inspect
celery -A celery_app inspect active
celery -A celery_app inspect ping
```

---

## 17. KEY ENVIRONMENT VARIABLES

```
MONGO_URL                   MongoDB connection string
DB_NAME                     MongoDB database name
REDIS_URL                   Redis connection string (redis://localhost:6379/0)
JWT_SECRET                  HS256 signing key (fallback auth)
FIREBASE_STORAGE_BUCKET     Firebase Storage bucket (optional; local disk if empty)
GOOGLE_CLIENT_ID/SECRET     YouTube OAuth
FACEBOOK_APP_ID/SECRET      Facebook/Instagram OAuth
TWITTER_CLIENT_ID/SECRET    Twitter OAuth
LINKEDIN_CLIENT_ID/SECRET   LinkedIn OAuth
RESEND_API_KEY              Email service
STRIPE_API_KEY              Stripe payments
RAZORPAY_KEY_ID/SECRET      Razorpay payments
FRONTEND_URL                Frontend URL (for email links)
SERVICE_URL                 Backend public URL (for constructing media URLs)
ENV                         "production" → JSON logs; otherwise colored console
```
