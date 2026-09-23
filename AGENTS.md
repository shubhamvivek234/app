# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v9.1 Prosp AI Architectural Advantages & Live Streaming Shipped
Branch: main
Focus: URL Deep-Linking & History Sync, Relational Cascades, Live SSE Stream, Convergent DAG

## Last Session Completed
Date: 2026-09-24
Completed:
- Campaign Save Visibility & Name Persistence: Fixed cross-origin session credentials on all outreach API requests (`credentials: 'include'`); added optimistic draft state synchronization between `OutreachCampaignWizard`, `OutreachApp`, and `OutreachCampaigns` for 0ms latency display; preserved custom names in drafts table and resume links; added fallback lookups in `auto_draft_campaign`.
- Sequence Canvas Orthogonal Grid Connectors: Replaced static 680px SVG and fixed 340px width constraints with responsive 2-column grid (`grid grid-cols-2 min-w-max`) and exact 50% orthogonal branch connectors; fixed misalignment where child branch cards were centered and detached from condition drop lines.
- 73/73 outreach tests pass, frontend CI clean (`CI=true npm run build`, 807.87 kB gzip main bundle).

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
