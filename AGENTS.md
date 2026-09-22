# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v8.5 LinkedIn Engage & Grow + Swipe Files Engine Shipped (Supergrow Parity)
Branch: main
Focus: Pre-Outreach Engagement Warmup, Tabless Feed, AI Comment Presets, Swipe Files & 1-Click Repurposer

## Last Session Completed
Date: 2026-09-23
Completed:
- Supergrow Video Forensic Analysis & MVP Implementation (`cuDI0NmpIh0`):
  - In-app 2-column Engage & Grow studio (`/outreach/engage`) with list management & CSV/URL prospect ingestion.
  - In-line post feed with 1-click Like, Comment, Discard, and Auto-Like pairing (`auto_like_and_comment`).
  - Contextual AI Comment Generator with 5 tone archetypes (*Insightful, Supportive, Humorous, Questioning, Challenger*).
  - Swipe Files gallery (`/outreach/swipe-files`) with tag filtering, search, and 1-click AI repurposing to outbound hooks/posts.
  - Backend models & endpoints in `outreach/api/engage.py`, `styles.py`, `swipe.py`, and `voyager_client.py`.
- 53/53 outreach tests pass, frontend CI clean (807 kB gzip main bundle).

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
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/ -q
.venv/bin/python -m compileall api/routes/ai.py utils/free_llm_router.py utils/content_repurposer.py
```
