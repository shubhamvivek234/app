# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Amazon SES Migration & Onboarding Welcome Email

## Last Session Completed
Date: 2026-09-05
Completed:
- Amazon SES Migration & Production Access: Fully migrated from Resend to AWS SES (`boto3`). AWS approved production access (`Status: GRANTED`, Case `178862046200763`) with 50,000 emails/day quota at 14 emails/sec.
- Rich Onboarding Welcome Email (`utils/notification_emails.py`): Responsive, agency-grade design featuring brand logo, 6-feature showcase grid (15 GB video, LinkedIn suite, AI repurposer, campaigns & recycling, smart bio, team approvals), 3-step quickstart, and prominent primary CTA.
- Test Suite & Build: 350/350 backend tests passing; frontend build clean; live delivery verified in production container.

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
