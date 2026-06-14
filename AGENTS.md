# SocialEntangler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v2.9 shipped
Branch: main
Focus: important notifications + composer reliability + R2 migration

## Last Session Completed
Date: 2026-06-14
Completed:
- Backend: added central important-notification emitter and consistent doc shape with event/type/title/severity/target/dedup/read fields.
  Files: `utils/notifications.py`, `utils/notification_prefs.py`
- Backend: wired schedule confirmations, aggregate publish results, reconnect-required, billing failed, and subscription-expiry/grace notices to the central emitter.
  Files: `api/routes/posts.py`, `celery_workers/tasks/publish.py`, `utils/ghost_cascade.py`, `api/routes/webhooks.py`, `celery_workers/tasks/subscription_check.py`
- Backend: normalized notification list/read/delete and dashboard activity to in-app important events only, with legacy `read` compatibility.
  Files: `api/routes/notifications.py`, `api/routes/dashboard.py`
- Frontend: rebuilt notification center to use shared API helpers and updated Settings notification categories/defaults.
  Files: `frontend/src/components/NotificationCenter.js`, `frontend/src/lib/api.js`, `frontend/src/pages/Settings.js`
- Tests: added focused notification tests and updated dashboard/reconnect fixtures.
  Files: `tests/test_settings_notifications.py`, `tests/test_dashboard_overview.py`, `tests/test_youtube_oauth_and_reconnect.py`

## Active Work
Currently implementing: None
Next:
- Commit/deploy the notification repair once requested and verify live notification center after first scheduled/published/failed events.
- Finish Cloudflare R2 migration (direct-to-R2 presigned uploads) and eliminate any remaining local-disk media paths.

## Deploy Notes
- Frontend: Vercel auto-deploys from `main`.
- Backend: EC2 `ubuntu@51.20.210.184` at `/opt/socialentagler`:
  `docker compose --env-file backend/.env -f docker-compose.prod.yml up -d --build`

## Quick Checks
```bash
git status --short
CI=true npm run build --prefix frontend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/test_settings_notifications.py tests/test_youtube_oauth_and_reconnect.py tests/test_dashboard_overview.py tests/test_post_reschedule_update.py tests/test_accounts_route.py -q
.venv/bin/python -m compileall api/routes/notifications.py api/routes/dashboard.py api/routes/posts.py celery_workers/tasks/publish.py utils/notifications.py utils/notification_prefs.py
```
