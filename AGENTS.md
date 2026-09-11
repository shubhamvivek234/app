# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-11
Completed:
- Smart Bio Per-Page Theme Isolation & Avatar Upload:
  - Fixed theme bleed between Page 1 and sub-pages in Studio preview and live public Smart Bio.
  - Added `theme` and `avatar_url` fields to `BioSubPage` backend Pydantic models.
  - Implemented `/api/bio-pages/avatar` upload endpoint with format/size validation and async storage.
  - Added Display Picture upload UI in `BioOutlineTree.js` and `BioInspectorDrawer.js` (both main and sub-page).
  - Isolated active theme updates and transitions synchronously in `LinkInBio.js` and `PublicBioPage.js`.
  - Verified with 373 unit tests (`pytest`) and frontend production build (`npm run build`).

## Active Work
Currently implementing: None
Next:
- Deploy backend to EC2 and verify live behavior on production.

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
