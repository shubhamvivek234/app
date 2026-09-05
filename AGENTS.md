# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Amazon SES Migration & Onboarding Welcome Email

## Last Session Completed
Date: 2026-09-06
Completed:
- Amazon SES Migration & Production Access: Fully migrated to AWS SES (`boto3`). Production access approved (`Status: GRANTED`, Case `178862046200763`) with 50,000 emails/day quota at 14 emails/sec.
- Welcome Email Redesign (`utils/notification_emails.py`, `api/deps.py`, `docker/Dockerfile.api`, `celery_workers/tasks/notifications.py`):
  - Fixed duplicate logo text (removed redundant adjacent text span).
  - Removed "15 GB" text from multi-platform publishing feature.
  - Eliminated repetitive copy; elevated visual aesthetic to minimalist, high-end agency standard (Stripe/Linear-style clean card, 4px top jewel accent strip, pastel geometric glyph badges, sleek numbered onboarding timeline, and obsidian CTA button).
  - Fixed API container build to bundle `celery_workers` & resolved DB name in notification Celery task (`DB_NAME=social_prod`).
- Test Suite & Live Delivery: All unit tests passing; live delivery verified and delivered to `findbinduprasad@zohomail.in` via Amazon SES.

## Active Work
Currently implementing: None
Next:
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
