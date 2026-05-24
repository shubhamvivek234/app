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
- Backend: versioned the local publish limiter for platforms that still use it, and removed the false per-account YouTube local limiter so uploads rely on real Google API responses plus the circuit breaker instead of an inaccurate internal token bucket.
  Files: `utils/rate_limit.py`, `platform_adapters/youtube.py`
- Backend: propagated precise local rate-limit retry windows to all platform adapters that use `check_rate_limit`.
  Files: `platform_adapters/facebook.py`, `platform_adapters/instagram.py`, `platform_adapters/linkedin.py`, `platform_adapters/threads.py`, `platform_adapters/tiktok.py`, `platform_adapters/twitter.py`
- Tests: added regressions for fallback timing, 429 classification, retryable pre-upload state handling, and waiting on an existing pre-upload retry.
  Files: `tests/test_publish_dispatch.py`

## Active Work
Currently implementing: None
Next:
- Verify EC2 deploy for the new rate-limit/publish retry fix on a fresh YouTube video post.
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
python3 -m compileall celery_workers/tasks/publish.py
```
