# SocialEntangler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v2.9 shipped
Branch: main
Focus: R2 migration + composer reliability + onboarding reliability

## Last Session Completed
Date: 2026-05-25
Completed:
- Backend: fixed YouTube/video publishes stuck in `processing` by delaying fallback child dispatch behind the primary queue, classifying `PlatformAPIError(code=429)` correctly, and preserving retryable pre-upload states as `retrying` instead of `failed`.
  Files: `celery_workers/tasks/publish.py`, `platform_adapters/base.py`
- Backend: removed the false local YouTube publish limiter and now rely on real Google API responses plus the circuit breaker for upload flow.
  Files: `utils/rate_limit.py`, `platform_adapters/youtube.py`
- Backend: pre-upload auth failures (for example YouTube `401 Invalid Credentials` during resumable-upload init) now attempt on-demand token refresh before reconnect/fail handling.
  Files: `celery_workers/tasks/publish.py`
- Backend: fixed async event-loop reuse across Celery worker tasks by introducing a shared per-process async runner and removing ad-hoc `asyncio.run(...)` / `run_until_complete(...)` wrappers.
  Files: `celery_workers/async_runner.py`, `celery_workers/tasks/*`, `db/mongo.py`, `db/redis_client.py`
- Backend: fixed token refresh comparisons for naive `token_expiry` values so refresh no longer crashes with `can't compare offset-naive and offset-aware datetimes`.
  Files: `celery_workers/tasks/tokens.py`
- Backend: fixed YouTube pre-upload refresh requeue state so a successful token refresh clears stale pre-upload state instead of leaving the publish worker in an infinite `pending` retry loop; publish-task retries now preserve `dispatch_source`.
  Files: `celery_workers/tasks/publish.py`
- Tests: added token refresh regressions and kept publish-dispatch regressions passing.
  Files: `tests/test_tokens.py`, `tests/test_publish_dispatch.py`

## Active Work
Currently implementing: None
Next:
- Verify EC2 deploy for the shared async-runner + token-refresh fixes on a fresh YouTube video post.
- Finish Cloudflare R2 migration (direct-to-R2 presigned uploads) and eliminate any remaining local-disk media paths.

## Deploy Notes
- Frontend: Vercel auto-deploys from `main`.
- Backend: EC2 `ubuntu@51.20.210.184` at `/opt/socialentagler`:
  `docker compose --env-file backend/.env -f docker-compose.prod.yml up -d --build`

## Quick Checks
```bash
git status --short
CI=true npm run build --prefix frontend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests --ignore=tests/sandbox -q
python3 -m compileall celery_workers/tasks/publish.py celery_workers/tasks/tokens.py celery_workers/async_runner.py
```
