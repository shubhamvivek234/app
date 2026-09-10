# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-11
Completed:
- Twitter v2 & Media Lifecycle Remediation:
  - Migrated Twitter media upload from legacy v1.1 chunked endpoint to modern Twitter API v2 (`/2/media/upload`) with OAuth 2.0 PKCE support and 402 Credits Depleted handling.
  - Implemented 48-Hour Failed Post Media Grace Period:
    - Updated `publish.py`: `should_cleanup_media()` only triggers immediate cleanup for fully successful posts; failed posts retain media and receive `failed_media_expires_at = now + 48h`.
    - Added `publish_to_platform` media rehydration from `db.media_assets` when retrying.
    - Updated `cleanup.py`: added `cleanup_expired_failed_posts_media()` task to delete expired media from Cloudflare R2 across all tiers once 48h elapse.
    - Updated `scheduler.py`: scheduled hourly scanner for expired failed post media.
    - Updated `posts.py`: `POST /posts/{post_id}/retry` re-hydrates media on retry within 48h, and guards against expired media with an HTTP 409 error.
    - Added `tests/test_failed_post_media_grace_period.py` (4/4 passed).

## Active Work
Currently implementing: None
Next:
- Implement Cluster B (Monetization Engine / Invoicing & Subscriptions) or deploy Cluster A to production.

## Deploy Notes
- Frontend: Vercel auto-deploys from `main`.
- Backend: EC2 `ubuntu@51.20.210.184` at `/opt/socialentagler`:
  `docker compose --env-file backend/.env -f docker-compose.prod.yml up -d --build`

## Quick Checks
```bash
git status --short
CI=true npm run build --prefix frontend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/ -q
.venv/bin/python -m compileall api/routes/ai.py utils/free_llm_router.py utils/content_repurposer.py
```
