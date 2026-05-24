# SocialEntangler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v2.9 shipped
Branch: main
Focus: R2 migration + composer reliability + onboarding reliability

## Last Session Completed
Date: 2026-05-24
Completed:
- Backend/Frontend: expanded YouTube analytics tabs with watch quality, demographics, retention, device/source breakdowns, and geography fallback metadata.
  Files: `api/routes/analytics.py`, `backend/app/social/google.py`, `frontend/src/pages/Analytics.js`
- Backend/Frontend: implemented Publish Inbox capability routing for supported DM/comment platforms and fixed Instagram DM display-name fallback.
  Files: `api/routes/inbox.py`, `backend/app/social/instagram.py`, `frontend/src/pages/Publish.js`, `frontend/src/lib/api.js`
- Frontend: fixed composer file picker so both dropzone and CTA text use the same trigger path.
  File: `frontend/src/components/composer/PlatformEditor.js`
- Backend/Frontend: fixed content-library published-post filtering/account mapping and timeslot auto-scheduling flows.
  Files: `api/routes/posts.py`, `api/routes/bulk_upload.py`, `utils/timeslots.py`, `frontend/src/pages/ContentLibrary.js`, `frontend/src/pages/Timeslots.js`
- Backend: hardened publish pipeline for orphaned child tasks, video fallback dispatch, and stale publish-lock recovery with explicit dispatch/receipt logs.
  Files: `celery_workers/tasks/publish.py`, `celery_workers/tasks/poll_status.py`

## Active Work
Currently implementing: None
Next:
- Verify EC2 deploy for publish-pipeline fixes and inspect fresh worker logs if any platform still remains in `processing`.
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
