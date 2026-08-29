# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v2.9 shipped
Branch: main
Focus: Unravler brand standardization + Master Product Roadmap

## Last Session Completed
Date: 2026-08-29
Completed:
- Master Product Roadmap: documented 11 key platform features across 4 tiers in `docs/MASTER_PRODUCT_ROADMAP.md` (Auto-UTM & Link Shortener, Link-in-Bio, Client Magic Links, Inline Draft Comments, PDF Reports, Evergreen Buckets, AI Brand Voice).
- Unravler Brand Standardization: updated FastAPI API title (`Unravler API`), CSV templates (`unravler_bulk_template.csv`), bot User-Agent (`Unravler-Bot/1.0`), support emails (`support@unravler.com`), and dual webhook signature headers (`X-Unravler-Signature` / `X-SocialEntangler-Signature`).
- RSS Feeds & Automations Engine: built and deployed RSS/Atom parser, REST API, Celery Beat poller, and frontend UI to production.
- Production Deploy: verified EC2 container cluster and Vercel production bundle (`unravler.com`).

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
