# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Amazon SES Migration & Onboarding Welcome Email

## Last Session Completed
Date: 2026-09-05
Completed:
- Amazon SES Migration (`utils/email_service.py`, `utils/auth_emails.py`, `utils/notification_emails.py`): Unified email delivery engine supporting Amazon SES (`boto3`) with automatic EC2 IAM role discovery and Resend backwards-compatible fallback.
- Welcome Email Hook (`api/deps.py`, `utils/notification_emails.py`, `utils/notification_prefs.py`): Automatically dispatches branded `user.welcome` onboarding email upon new user registration.
- Unified Docker Configuration (`docker-compose.prod.yml`, `docker-compose.yml`): Configured `EMAIL_PROVIDER`, `AWS_SES_REGION`, and credentials for production deployment.
- Test Suite: 350/350 backend tests passing (8 new tests in `test_email_service.py`); frontend production build clean.

## Active Work
Currently implementing: None
Next:
- Monitor AWS SES Production Access approval (request submitted, status PENDING).
- Verify custom link domain in Firebase if desired for 100% white-label auth URLs.

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
