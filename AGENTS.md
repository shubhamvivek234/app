# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v3.6 shipped
Branch: main
Focus: Full Outbound & Inbound Webhooks Engine, HMAC Signatures, Native Slack/Discord Embed Formatting, Delivery History & Test Ping Suite, and Interactive Developer Portal

## Last Session Completed
Date: 2026-09-01
Completed:
- Outbound Webhooks Pipeline (`api/routes/user_webhooks.py`, `celery_workers/tasks/publish.py`, `api/routes/posts.py`): Connected event streaming for `post.published`, `post.failed`, `post.scheduled`, `post.cancelled`, `account.disconnected`, and `post.approval_requested` with HMAC-SHA256 signing and SSRF protection.
- Slack & Discord Native Adapters: Auto-detects Slack/Discord webhooks and formats payloads into rich BlockKit sections / color-coded Discord Embeds.
- Interactive Webhook Management Portal (`pages/Developers.js`, `lib/api.js`): Subscribed event checkboxes, one-time signing secret modal, instant test-ping runner (`POST /test`), delivery logs drawer, and Inbound Webhook generator for Zapier, Make, n8n, Airtable.
- Tests & Deployment: 278/278 tests passing (100%), frontend production build compiled cleanly, committed to `main` (Vercel), and deployed to EC2 (`{"status":"ok"}`).

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
