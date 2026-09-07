# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-08
Completed:
- Transactional & Notification Email Branding: Configured high-resolution official Unravler logos (`unravler-logo-dark.png` and `unravler-logo-white.png`) with public HTTPS fallback (`https://www.unravler.com/...`) across all email generators (`utils/auth_emails.py`, `utils/notification_emails.py`, `backend/celery_tasks.py`, `backend/server.py`).
- Email Robustness: Prevented broken `localhost` images in customer inboxes when `FRONTEND_URL` is set to local dev; wrapped headers in clickable links with explicit retina dimensions and alt text; updated magic link and approval notification templates to full branded card layouts.
- Test Coverage: Added unit tests in `tests/test_auth_security.py` and `tests/test_email_service.py` verifying logo URL resolution and HTML rendering.

## Active Work
Currently implementing: None
Next:
- Monitor email delivery, logo rendering across email clients (Gmail/Apple Mail/Outlook), and verification conversions.

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
