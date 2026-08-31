# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v3.4 shipped
Branch: main
Focus: Transactional Email Notification Engine (Resend Integration & Celery Worker), User Preference Enforcement, Notification Center Modernization, and Full Application Dark Theme Overhaul

## Last Session Completed
Date: 2026-08-31
Completed:
- Outbound Email Dispatcher (`utils/notification_emails.py`): Responsive HTML email templates with severity color accents, deep-link CTAs, and Resend delivery via `resend.Emails.send`.
- Async Celery Worker Task (`celery_workers/tasks/notifications.py`): `send_notification_email_task` with strict user settings preference gating (`should_notify(db, user_id, event, "email")`).
- In-App Notification Center (`components/NotificationCenter.js`, `api/routes/notifications.py`): Added category filtering tabs (`all`, `unread`, `publishing`, `system`), bulk clear-all endpoint (`DELETE /api/v1/notifications/clear-all`), and in-item quick actions.
- Dark Theme Overhaul across all primary application views: NotificationCenter, Dashboard, Calendar, CreatePostForm (Composer, PlatformEditor, AccountSelector, Voice Memo drawer, bottom bar), Social Inbox, Connected Accounts, and Analytics.
- Tests & Deployment: 276/276 tests passing (100%), frontend production build compiled cleanly, committed to `main` (Vercel), and deployed to EC2 (`Up (healthy)`).

## Active Work
Currently implementing: None
Next:
- Implement legal & app verification roadmap (`docs/APP_VERIFICATION_AND_LEGAL_PLAN.md`) when business details are provided.

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
