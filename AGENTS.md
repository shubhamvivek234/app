# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v4.8 shipped
Branch: main
Focus: Gemini Aurora Living Mesh Flowing Gradient on Sidebar Create Post Button

## Last Session Completed
Date: 2026-09-02
Completed:
- Gemini Aurora Living Flowing Gradient (`frontend/src/index.css`, `frontend/src/components/DashboardLayout.js`):
  - Added continuous 350% fluid gradient animation cycling through Electric Violet, Radiant Coral, Amber Glow, Cobalt, and Deep Indigo.
  - Added dual-layer glowing halo (`gemini-aurora-glow`) with Gaussian blur that pulses and projects ambient colored light.
  - Inset specular glass reflection and tactile micro-interactions on hover and active click.
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
