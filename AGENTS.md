# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v9.1 Prosp AI Architectural Advantages & Live Streaming Shipped
Branch: main
Focus: URL Deep-Linking & History Sync, Relational Cascades, Live SSE Stream, Convergent DAG

## Last Session Completed
Date: 2026-09-23
Completed:
- Unified Inbox Parity & Unravler Branding: Replaced all leftover Prosp references in `DashboardLayout.js` navigation badge and `prompts.py` with Unravler.
- Inbox Functionality Overhaul: Added toast alerts across all actions (replies, reminders, snippets, tags, intent), top-bar live sync button, automatic first-thread selection, Escape key modal dismiss, safe avatar initial fallback, and demo conversation seeding endpoint (`POST /seed-demo`).
- Account Resolution & Sync Resilience: Fixed `sync_all_accounts` query to check both `workspace_id` and `user_id`; made `send_thread_reply` account fallback resilient for demo/mock testing.
- 71/71 outreach tests pass, frontend CI clean (`CI=true npm run build`, 807.88 kB gzip main bundle).

## Active Work
Currently implementing: None
Next:
- Sequence pre-warming automation (`LIKE_LAST_POST`, `COMMENT_LAST_POST` in executor).
- Content Writing Styles UI (`OutreachStyles.js`).
- Auto-Plug scheduled first comments in post composer.

## Deploy Notes
- Frontend: Vercel auto-deploys from `main`.
- Backend: EC2 `ubuntu@51.20.210.184` at `/opt/socialentagler`:
  `docker compose --env-file backend/.env -f docker-compose.prod.yml up -d --build`

## Quick Checks
```bash
git status --short
CI=true npm run build --prefix frontend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/test_outreach*.py -q
.venv/bin/python -m compileall api/routes/ai.py utils/free_llm_router.py utils/content_repurposer.py outreach/
```
