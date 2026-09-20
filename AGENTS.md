# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.1 shipped
Branch: main
Focus: Full Postiz Feature Parity (Developer Settings, Scoped Webhooks, RSS Auto-Post, Video Clipper, AI Agent Hub, CLI)

## Last Session Completed
Date: 2026-09-20
Completed:
- Postiz Feature Parity End-to-End:
  - Developer Settings & Scoped Webhooks: OAuth2 Apps management, token scopes, MCP JSON generator, and account-filtered webhook dispatches.
  - RSS Auto-Post & CLI / Skill: Backfill/sync toggle, AI picture generator via Pollinations, official Unravler CLI (`cli/bin/unravler.js`), and Agent Skill definition.
  - Video Clipping Engine: YouTube timedtext parsing, viral moment heuristic scoring, ASS vertical 9:16 subtitle burning, Celery background renderer, and `VideoClipperModal.js`.
  - AI Agent Hub: 3-pane chat interface at `/agent` with session persistence, channel guardrail, and interactive action cards (Composer draft, Video Clipper, Banner generator).
  - Fixed PII log scrubber primitive type preservation in `utils/log_scrub.py`.
  - All 423 backend unit tests and frontend production CI build passed clean.

## Active Work
Currently implementing: None
Next:
- Deploy updates to production.

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
