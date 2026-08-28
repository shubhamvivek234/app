# SocialEntangler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v2.9 shipped
Branch: main
Focus: important notifications + composer reliability + R2 migration

## Last Session Completed
Date: 2026-08-29
Completed:
- Backend & Public API: added Timeslots (`GET /public/timeslots`, `GET /public/timeslots/next-slot`) and Webhooks (`GET`, `POST`, `DELETE`, `POST /test`) to the Developer Public API; added `webhooks:manage` scope and support for `scheduled_time` and `timeslot_category` (`api/routes/public_api.py`, `utils/developer_tokens.py`, `tests/test_public_api.py`).
- Frontend & Developers Docs: updated curl snippets and REST reference tables for Approvals, Timeslots, and Webhooks (`frontend/src/pages/Developers.js`).
- Frontend & Settings: expanded timezone coverage across global IANA regions (`frontend/src/pages/Settings.js`).
- Backend & Roles: implemented `approval:decide` permission for `Client` role, allowing invited clients to review, approve, and reject posts end-to-end without needing full workspace edit privileges (`utils/roles.py`, `api/routes/posts.py`, `api/routes/auth.py`, `api/routes/team.py`).
- Backend: enhanced reviewer notification targeting to include client members and assigned reviewers with 7-day magic login tokens (`api/routes/posts.py`).
- Backend & Frontend: implemented timezone-aware timeslot resolution using Python ZoneInfo (`utils/timeslots.py`, `api/routes/timeslots.py`, `api/routes/posts.py`, `api/routes/bulk_upload.py`), eliminating UTC offset drift.
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
