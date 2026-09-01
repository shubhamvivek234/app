# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v4.9 shipped
Branch: main
Focus: Ethereal Pastel Gemini Aurora Living Color Glow on Sidebar Create Post Button

## Last Session Completed
Date: 2026-09-02
Completed:
- Ethereal Pastel Gemini Palette (`frontend/src/index.css`, `frontend/src/components/DashboardLayout.js`):
  - Calibrated gradient to soft, luminous pastel Gemini shades: Ethereal Indigo (#6366F1), Radiant Orchid (#A855F7), Pastel Rose (#FB7185), Warm Amber Pearl (#FBBF24), Crystal Sky (#38BDF8), and Lavender (#818CF8).
  - Enhanced ambient Gaussian blur projection (`filter: blur(14px)`) and reinforced high-contrast typography and subtle glass specular reflection.
- Tests & Deployment: Frontend build compiled cleanly with 0 errors, pushed to origin/main and deployed to EC2.

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
