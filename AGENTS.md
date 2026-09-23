# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v9.1 Prosp AI Architectural Advantages & Live Streaming Shipped
Branch: main
Focus: URL Deep-Linking & History Sync, Relational Cascades, Live SSE Stream, Convergent DAG

## Last Session Completed
Date: 2026-09-23
Completed:
- URL Deep-Linking & Browser History: Wired native `window.location.search`, `pushState`, and `popstate` Back/Forward navigation across `OutreachApp.js` and `OutreachCampaigns.js`.
- Relational Cascade Integrity: Shipped atomic cascade hooks in `campaigns.py` (cancels tasks, unenrolls leads, archives sequence) and `accounts.py` (unbinds disconnected sender accounts from campaign pools, cancels assigned tasks) with full reversible restore.
- Real-Time Activity SSE Stream: Shipped `/api/v1/outreach/analytics/live-feed` SSE endpoint and live activity pulse listener in `OutreachHome.js` ($0.00 infra cost).
- Converging Branches in DAG Engine: Verified multi-branch convergence into shared steps with Kahn's algorithm and `execution_order` tracking in `dag_compiler.py`.
- 69/69 outreach tests pass, frontend CI clean (`CI=true npm run build`, 807.89 kB gzip main bundle).

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
