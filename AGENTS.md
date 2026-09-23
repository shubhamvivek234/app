# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v9.1 Prosp AI Architectural Advantages & Live Streaming Shipped
Branch: main
Focus: URL Deep-Linking & History Sync, Relational Cascades, Live SSE Stream, Convergent DAG

## Last Session Completed
Date: 2026-09-24
Completed:
- Campaigns Section Overhaul & Lifecycle Actions: Added `duplicate_campaign` backend endpoint (`POST /api/v1/outreach/campaigns/{id}/duplicate`) to clone sequence DAG, settings, schedule, and limits into a new draft; added Pause/Resume and Duplicate options to campaign 3-dot dropdown and Campaign Detail header.
- Dynamic Campaign Detail & Sequence Flow: Updated Tab 3 ("Sequence") to render actual sequence steps and delay cards from DAG; updated Tab 4 ("Settings") to dynamically reflect schedule, timezone, and daily limits; added quick Pause/Resume/Launch header controls.
- Wizard Step 1 Leads Sync & Preview: Added enrolled leads count badge, rich summary card, and preview table in Step 1; wired `onLeadsImported` on `ImportLeadsModal`; fixed auto-draft custom ID fallback persistence.
- Standardized `sonner` toasts across all campaign actions and purged all leftover Prosp comments.
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
