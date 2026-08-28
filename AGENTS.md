# SocialEntangler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v2.9 shipped
Branch: main
Focus: important notifications + composer reliability + R2 migration

## Last Session Completed
Date: 2026-08-29
Completed:
- Frontend: redesigned Hashtag Groups manager with clean pure-light minimalist architecture, collapsible AI generator drawer, streamlined card layout, and interactive 1-click tag copy feedback (`frontend/src/pages/HashtagGroups.js`).
- Frontend: refined brand loading animation to be full-screen centered with pure-black Unravler logo mark, staggered ribbon wave motion, zero circular lines/arcs, and overlaying the entire viewport/sidebar (`frontend/src/components/BrandMarkLoader.js`, `Dashboard.js`, `CalendarView.js`).
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
