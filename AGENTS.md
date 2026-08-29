# SocialEntangler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v2.9 shipped
Branch: main
Focus: important notifications + composer reliability + R2 migration

## Last Session Completed
Date: 2026-08-29
Completed:
- RSS Feeds & Automations Engine: built SSRF-protected XML/Atom/YouTube parser (`utils/rss_parser.py`), REST API (`api/routes/rss_feeds.py`), Celery Beat polling task (`celery_workers/tasks/rss_poller.py`), frontend page & API client (`frontend/src/pages/RSSFeeds.js`, `frontend/src/lib/api.js`, `frontend/src/components/DashboardLayout.js`), and comprehensive test suite (`tests/test_rss_feeds.py`).
- Bulk Upload Engine & API: implemented `POST /bulk/validate-urls` (SSRF-guarded pre-flight media validator), aligned `POST /bulk/csv-schedule` and `/bulk/csv-upload`, fixed full MongoDB document schema (`id`, `post_id`, `version: 1`, `platform_results`, `account_results`, `status_history`, `content_hash`), and flexible account name/username/ID resolution (`api/routes/bulk_upload.py`, `tests/test_bulk_upload.py`).
- Frontend Bulk CSV & Video: migrated `BulkCSVUpload.js`, `BulkVideoUpload.js`, and `BulkCSVModal.js` from stale `localStorage` tokens to centralized Firebase auth API client (`frontend/src/lib/api.js`, `frontend/src/pages/BulkCSVUpload.js`, `frontend/src/pages/BulkVideoUpload.js`, `frontend/src/components/BulkCSVModal.js`).
- Backend & Public API: added Timeslots & Webhooks endpoints, updated developer docs & token scopes (`api/routes/public_api.py`, `utils/developer_tokens.py`, `frontend/src/pages/Developers.js`).
- Backend & Roles: implemented `approval:decide` permission for `Client` role (`utils/roles.py`, `api/routes/posts.py`, `api/routes/auth.py`, `api/routes/team.py`).
- Master Legal & App Verification Plan documented in `docs/APP_VERIFICATION_AND_LEGAL_PLAN.md`.

## Active Work
Currently implementing: None
Next:
- Implement legal & app verification roadmap (`docs/APP_VERIFICATION_AND_LEGAL_PLAN.md`) when business details are provided.
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
