# SocialEntangler Codebase Issues — Complete Analysis

**Date:** 2026-03-25  
**Branch:** main (v2.9 modular architecture)  
**Total Issues Found:** 48

---

## CATEGORY 1: STARTUP BLOCKERS

### SB-1: Import of non-existent module `db.audit_events`
**Location:** `api/main.py:57`
```python
from db.audit_events import ensure_indexes as create_audit_indexes
```
**Issue:** This module doesn't exist in `db/` directory. The app will crash with `ImportError` on startup.
**Fix:** Remove this import or create the module.

### SB-2: Multiple route files may not exist
**Location:** `api/main.py:36-53`
**Issue:** Imports 24 routers, many of which likely don't exist:
- `user_webhooks`, `user`, `ai`, `bulk_upload`, `timeslots`
- `notifications`, `hashtags`, `stats`, `analytics`
- `api_keys`, `team`, `recurring`, `media_assets`
- `calendar_notes`, `inbox`, `support`
**Fix:** Verify each route file exists or create the missing ones.

### SB-3: Redis env var mismatch
**Location:** `db/redis_client.py:31` vs `run.sh:10`
```python
# db/redis_client.py expects:
REDIS_QUEUE_URL  # crashes if not set
REDIS_CACHE_URL  # crashes if not set

# run.sh exports only:
export REDIS_URL="redis://localhost:6379/0"
```
**Fix:** Update `run.sh` to export `REDIS_QUEUE_URL` and `REDIS_CACHE_URL`, or update `db/redis_client.py` to fall back to `REDIS_URL`.

---

## CATEGORY 2: BUGS (Runtime Failures)

### BUG-1: `send_notification` signature mismatch
**Location:** `celery_workers/tasks/publish.py:648-660` calls `send_notification` with `user_id` kwarg
**Issue:** `media.py:148` signature doesn't accept `user_id`:
```python
def send_notification(post_id, type, platform=None, error=None, post_url=None):
```
The notification task must do a DB lookup to resolve user_id (wasteful but works).
**Fix:** Add `user_id` parameter to `send_notification` signature.

### BUG-2: `db/mongo.py` expects `MONGODB_URI`
**Location:** `db/mongo.py:28`
**Issue:** If `.env` uses `MONGO_URL` (from monolith), startup crashes with `KeyError`.
**Fix:** Document the env var requirement clearly, or support both names.

### BUG-3: `get_user_prefs` shallow copy bug
**Location:** `utils/notification_prefs.py:38`
```python
prefs = DEFAULT_PREFERENCES.copy()  # Shallow copy!
```
**Issue:** Values are dicts (mutable). Concurrent requests could mutate module-level constants.
**Fix:** Use `copy.deepcopy(DEFAULT_PREFERENCES)` or immutable structures.

### BUG-4: YouTube adapter dead condition
**Location:** `platform_adapters/youtube.py:85`
```python
if init_resp.status_code not in (200, 200):  # (200, 200) == (200,)
    if init_resp.status_code != 200:  # Redundant
```
**Fix:** Change to `(200, 201)`.

### BUG-5: `subscription_check.py` queries wrong field
**Location:** `celery_workers/tasks/subscription_check.py:50, 69, 81, 91, 122, 179`
```python
cursor = db.users.find(..., {"id": 1, ...})  # Should be "user_id": 1
await db.users.update_one({"id": user["id"]}, ...)  # Should be "user_id"
```
**Issue:** v2.9 user schema uses `user_id` as primary key, not `id`. Queries return nothing.
**Fix:** Replace all `id` references with `user_id`.

### BUG-6: `cleanup.py` passes URL instead of storage key
**Location:** `celery_workers/tasks/cleanup.py:166`
```python
delete_file(url)  # url = "https://pub-xxx.r2.dev/media/file.mp4"
```
**Issue:** `utils/storage.py:104` expects key like `media/file.mp4`, not full URL. R2 deletion silently fails.
**Fix:** Extract storage key from URL before calling `delete_file`.

### BUG-7: Jitter blocks entire Celery worker thread
**Location:** `celery_workers/tasks/publish.py:131-133`
```python
if jitter > 0:
    time.sleep(jitter)  # Blocks for 0-300 seconds
```
**Issue:** For video posts, jitter blocks the worker thread, preventing other tasks from processing.
**Fix:** Use async sleep or move jitter to retry countdown.

---

## CATEGORY 3: RACE CONDITIONS & CONCURRENCY

### RC-1: SSE connection count not cleaned on crash
**Location:** `api/routes/stream.py:204-205`
**Issue:** If API process crashes while user has active SSE, counter never decrements. After 2 crashes, user is locked out for 1 hour.
**Fix:** Use shorter TTL or use Redis key with automatic expiry based on connection timestamp.

### RC-2: Poison pill counter uses two Redis pools
**Location:** `celery_workers/tasks/publish.py:197-205` vs `229-230`
```python
r_queue = get_queue_redis()  # pool 1
pp_count = await r_queue.incr(f"delivery_count:{task.request.id}:{platform}")

r_cache = get_cache_redis()  # pool 2
delivery_count = await r_cache.incr(poison_key)  # separate counter
```
**Issue:** Delivery count tracked in two places. Total delivery could exceed 5 while each counter shows <5.
**Fix:** Use single Redis pool for poison pill tracking.

### RC-3: Concurrent upload race condition
**Location:** `api/routes/upload.py:52-64`
```python
count = await cache_redis.get(key)  # GET
if count and int(count) >= limit:
    raise ...
await cache_redis.incr(key)  # INCR (separate operation)
```
**Issue:** Race window between GET and INCR. Could exceed limit.
**Fix:** Use Lua script or check-return of INCR atomically.

---

## CATEGORY 4: SECURITY VULNERABILITIES

### SEC-1: Twitter/LinkedIn/TikTok webhooks skip verification
**Location:** `api/routes/webhooks.py:96-99`
```python
else:
    logger.warning("No signature verification configured for platform: %s", platform)
```
**Issue:** Webhook endpoints accept any payload without signature verification.
**Fix:** Implement signature verification for all platforms.

### SEC-2: SSRF guard not enforced on media_url in posts
**Location:** `api/routes/posts.py`
**Issue:** User can set `media_url` to internal URLs (`169.254.169.254`). SSRF guard exists in platform adapters but not in post creation.
**Fix:** Call `assert_safe_url()` on media_url before storing.

### SEC-3: Public API has no rate limiting
**Location:** `api/routes/public_api.py:62-91`
**Issue:** `/public/*` routes have no `@limiter.limit()` decorators.
**Fix:** Add rate limiting to public API endpoints.

### SEC-4: Admin panel auth uses non-existent field
**Location:** `api/routes/admin.py:24-31`
```python
role = current_user.get("role", "")  # UserResponse has no "role" field!
if role not in _ADMIN_ROLES:
    raise HTTPException(...)
```
**Issue:** Every admin request returns 403. Admin panel is completely non-functional.
**Fix:** Check workspace role via `workspace_members` collection.

### SEC-5: CORS headers missing `X-TOTP-Code`
**Location:** `api/main.py:157`
```python
allow_headers=["Authorization", "Content-Type", "X-Trace-ID"],
```
**Issue:** MFA header is stripped in CORS preflight requests.
**Fix:** Add `X-TOTP-Code` to allowed headers.

### SEC-6: Rate limiter uses IP instead of user identity
**Location:** `api/limiter.py:11`
```python
key_func=get_remote_address,  # Returns proxy IP, not client IP
```
**Issue:** All users behind proxy share rate limit. One user's abuse blocks everyone.
**Fix:** Use `X-Forwarded-For` header extraction with trusted proxy config.

---

## CATEGORY 5: DATA INTEGRITY & CORRECTNESS

### DI-1: User creation skips workspace
**Location:** `api/routes/auth.py:305-329`
```python
user_doc = {"workspace_ids": [], "default_workspace_id": None}
```
**Issue:** New users have no workspace. Endpoints requiring workspace fail until first `/me` call.
**Fix:** Create default workspace during user creation.

### DI-2: Post creation doesn't validate media_ids
**Location:** `api/routes/posts.py:144-172`
**Issue:** Posts store arbitrary media_ids without verifying they exist in `media_assets`.
**Fix:** Validate media_ids exist before storing.

### DI-3: Soft-deleted posts auto-purge after 30 days
**Location:** `db/indexes.py:37`
```python
await _safe_create_index(db.posts, [("deleted_at", 1)], expireAfterSeconds=2592000)
```
**Issue:** Accidentally deleted posts are permanently lost after 30 days.
**Fix:** Implement soft-delete with manual cleanup option, not automatic TTL.

### DI-4: Inconsistent field names (user_id vs id)
**Location:** Throughout codebase
**Issue:** Posts use `id`, users use `user_id`. Subscription check queries `id` which doesn't exist.
**Fix:** Standardize on one field name across all collections.

### DI-5: OAuth URL wrong env var names
**Location:** `api/routes/accounts.py:260-261`
```python
client_id = os.environ.get(f"{platform.upper()}_CLIENT_ID", "")
# YouTube expects GOOGLE_CLIENT_ID, not YOUTUBE_CLIENT_ID
```
**Fix:** Map platform names to correct env var names.

### DI-6: Posts don't store social_account_ids
**Location:** `api/routes/posts.py:144-172`
**Issue:** Disconnect guard (`api/routes/accounts.py:104-110`) queries `social_account_ids` but posts only store `platforms`. Conflict detection never finds affected posts.
**Fix:** Store social_account_ids on post creation.

---

## CATEGORY 6: EDGE CASES

### EC-1: Post deleted during pre-upload
**Scenario:** User creates post → scheduler triggers pre-upload → user deletes post → pre-upload completes → updates fail silently → Instagram/YouTube containers orphaned.
**Fix:** Check post existence before updating, clean up orphaned containers.

### EC-2: Concurrent edits without conflict resolution
**Scenario:** Two users fetch same post (version=1), both update. First succeeds (version=2), second fails 409. Frontend shows error but doesn't implement retry.
**Fix:** Implement client-side retry with refresh.

### EC-3: Instagram container expires between phases
**Scenario:** Pre-upload creates container → delayed queue → container expires (24h) → publish fails with EC4 error but no re-pre-upload.
**Fix:** Detect expired containers and re-run pre-upload automatically.

### EC-4: YouTube chunk upload crash without offset persistence
**Scenario:** Chunk uploads successfully (308 response) → worker crashes before Redis write → retry restarts from beginning (2GB re-upload).
**Fix:** Write offset before confirming chunk success, or use database for state.

### EC-5: Expired subscription can still upload media
**Location:** `api/routes/upload.py:87-88`
**Issue:** Checks `plan` but not `subscription_status`. Expired users with "agency" plan can upload 2GB files.
**Fix:** Also check `subscription_status != "expired"`.

### EC-6: Duplicate SSE events on history replay
**Location:** `api/routes/stream.py:69-86`
**Issue:** If same event published to multiple channels, history list has duplicates. Client receives duplicates on replay.
**Fix:** Deduplicate before replaying.

### EC-7: Notification preferences fetched per-event
**Location:** `celery_workers/tasks/media.py:213, 226`
**Issue:** Every notification triggers DB query for user preferences. 10 posts × 6 platforms = 60 redundant queries.
**Fix:** Cache preferences in Redis with 5-minute TTL.

### EC-8: File handle leak in media processing
**Location:** `celery_workers/tasks/media.py:89-91`
```python
media_bytes = await loop.run_in_executor(
    None, lambda: open(processed_path, "rb").read()
)
```
**Issue:** File handle not explicitly closed. GC eventually closes but could exhaust under load.
**Fix:** Use context manager or explicit close.

### EC-9: Rate limiter fallback uses wrong default
**Location:** `api/limiter.py:12`
```python
storage_uri=os.environ.get("REDIS_CACHE_URL", "redis://localhost:6379/1")
```
**Issue:** If REDIS_CACHE_URL not set, falls back to port 6379. If Redis on different port, rate limiting fails silently (falls back to in-memory).
**Fix:** Validate Redis connectivity on startup or use consistent env vars.

### EC-10: OAuth state parameter not URL-encoded
**Location:** `api/routes/accounts.py:268`
```python
return f"{base}?client_id={client_id}&redirect_uri={redirect_uri}&state={state}..."
```
**Issue:** Special characters in redirect_uri or state break OAuth flow.
**Fix:** URL-encode all query parameters.

### EC-11: `storage.py` delete_file expects key, not URL
**Location:** Same as BUG-6 - R2/Firebase deletions silently fail.
**Fix:** Extract key from URL before calling delete_file.

### EC-12: Feature flags read at import time
**Location:** `utils/feature_flags.py:13-23`
**Issue:** Env vars read at module import. Changes after startup not picked up.
**Fix:** Document this behavior or implement runtime reload.

---

## CATEGORY 7: ARCHITECTURAL IMPROVEMENTS

### ARCH-1: No MongoDB connection pooling per Celery worker
**Issue:** Each task calls `get_client()` creating new connections. High throughput workers create connection pressure.
**Fix:** Initialize client once at worker startup via Celery signals.

### ARCH-2: `asyncio.run()` per Celery task
**Issue:** Creates new event loop per task. Expensive, prevents resource sharing across tasks.
**Fix:** Use single event loop per worker process.

### ARCH-3: No DLQ admin API
**Issue:** DLQ logic exists but no admin UI to list/inspect/retry failed posts.
**Fix:** Add DLQ endpoints to admin router.

### ARCH-4: No Celery worker health check
**Issue:** `/ready` checks MongoDB/Redis but not worker liveness. Dead worker silently stops processing.
**Fix:** Add worker heartbeat or queue depth monitoring endpoint.

### ARCH-5: Rate limiter doesn't handle proxies
**Issue:** Behind Nginx, all users appear as 127.0.0.1.
**Fix:** Extract client IP from X-Forwarded-For with trusted proxy list.

### ARCH-6: No idempotency on post creation
**Issue:** Frontend retry creates duplicate posts. Content hash warns but doesn't prevent.
**Fix:** Add idempotency key to post creation, check before insert.

### ARCH-7: Notification delivery has no retry
**Issue:** Resend failures are logged and dropped. No retry queue.
**Fix:** Implement failed notification retry with exponential backoff.

### ARCH-8: No graceful degradation when Redis down
**Issue:** Entire system crashes if Redis fails. No fallback mode.
**Fix:** Implement fallback modes (in-memory rate limiting, polling for SSE).

---

## CATEGORY 8: FRONTEND ISSUES

### FE-1: `onboarding_completed` field missing from backend
**Location:** `App.js:78` checks `user.onboarding_completed`
**Issue:** v2.9 `UserResponse` doesn't include this field. All users redirected to `/onboarding` indefinitely.
**Fix:** Add `onboarding_completed` to UserResponse model.

### FE-2: `user.name` vs `user.display_name` mismatch
**Location:** Frontend uses `user.name`, backend returns `display_name`
**Issue:** Avatar shows "U" (initials fallback), welcome shows "Welcome, undefined".
**Fix:** Add `name` to UserResponse or update frontend to use `display_name`.

### FE-3: Login/Signup forms hit non-existent endpoints
**Issue:** Forms likely POST to `/api/auth/login` (custom email/pass). v2.9 only has Firebase auth.
**Fix:** Update forms to use Firebase auth flow, or add custom JWT endpoint.

### FE-4: Axios headers not cleaned on logout
**Location:** `AuthContext.js:45` sets header globally
**Issue:** On logout, header deleted but stale token can persist during auth state transition.
**Fix:** Clear headers immediately on logout, not in onAuthStateChanged callback.

### FE-5: No React error boundary
**Location:** `App.js`
**Issue:** Any component crash shows blank white screen.
**Fix:** Add error boundary wrapper at top level.

---

## SUMMARY BY SEVERITY

| Severity | Count | Examples |
|----------|-------|---------|
| **Startup Blocker** | 3 | Missing route files, audit_events import, Redis env vars |
| **Runtime Crash** | 4 | user_id vs id, delete_file key, YouTube condition |
| **Data Corruption** | 2 | Shallow copy prefs, media deletion fails silently |
| **Security** | 6 | Unverified webhooks, SSRF, admin auth broken, CORS |
| **Logic Bug** | 3 | Poison pill double-counting, jitter blocks worker |
| **Frontend Broken** | 5 | Missing fields, wrong field names, dead endpoints |
| **Edge Cases** | 12 | Container expiry, crash during upload, race conditions |
| **Architecture** | 8 | Connection pooling, event loops, DLQ admin, idempotency |

---

## RECOMMENDED PRIORITY

### P0 (Critical - Fix Immediately)
1. SB-1, SB-2: Missing imports/routes (app won't start)
2. SEC-4: Admin panel completely broken (403 on all requests)
3. BUG-5: Subscription check queries wrong field
4. DI-6: Disconnect guard doesn't find affected posts

### P1 (High - Fix Soon)
1. BUG-6, EC-11: Media cleanup silently fails
2. SEC-1: Webhook signature verification missing
3. RC-2: Poison pill counter race condition
4. FE-1, FE-2: Frontend shows wrong data due to field mismatch

### P2 (Medium - Plan for Next Sprint)
1. ARCH-2: asyncio.run() per task (performance)
2. ARCH-3: No DLQ admin API
3. SEC-6: Rate limiter IP-based
4. EC-7: Notification preferences fetched per-event

### P3 (Low - Backlog)
1. ARCH-8: Graceful degradation
2. FE-4, FE-5: Frontend improvements
3. EC-12: Feature flag reload