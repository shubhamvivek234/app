# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v5.0 shipped
Branch: main
Focus: Ultra-Light Ethereal Gemini Aurora Button & Smart Bio Card Real-Time Reactivity

## Last Session Completed
Date: 2026-09-02
Completed:
- Ultra-Light Gemini Aurora Button (`frontend/src/index.css`, `frontend/src/components/DashboardLayout.js`):
  - Calibrated gradient to dreamy ultra-light pastel shades: Moonlight Lavender (#E0E7FF), Lilac Bloom (#DDD6FE), Petal Rose (#FBCFE8), Warm Pearl (#FEF08A), Crystal Aqua (#BAE6FD), and Soft Periwinkle (#C7D2FE).
  - Paired with crisp obsidian typography (`text-slate-900`), indigo icon accent, and diffused ambient bloom (`filter: blur(16px)`).
- Smart Bio Card Background Color Fix (`frontend/src/lib/bioThemeUtils.js`, `frontend/src/pages/LinkInBio.js`, `frontend/src/pages/PublicBioPage.js`):
  - Updated `getTactileCardStyles` to respect `theme.card_bg` globally across all cards unless an explicit per-block custom background is toggled.
  - Card background, border, and text color changes now instantly reflect in live studio preview and on the published bio page.
- Tests & Deployment: Frontend build and 282 backend tests passed cleanly. Pushed to origin/main and synced on EC2.

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
