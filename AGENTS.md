# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v4.3 shipped
Branch: main
Focus: Smart Bio Studio Hyper-Realistic Machined iPhone 16 Pro Viewport & Studio Stage Elevation

## Last Session Completed
Date: 2026-09-02
Completed:
- Smart Bio Studio Preview Refinement (`frontend/src/pages/LinkInBio.js`):
  - Aerospace Titanium Chassis: Double-bezel frame with extruded hardware buttons (action, volume up/down, power) and concentric inner radius.
  - Interactive Dynamic Island: Glossy pill enclosure with sapphire camera reflection flare and TrueDepth sensor cutout.
  - iOS Status Bar: 9:41 clock, 5G badge, cellular signal bars, Wi-Fi wave, battery indicator with green charge fill.
  - Studio Stage Controls: Device switcher (iPhone 16 Pro, Tablet, Desktop), scale zoom slider (75%–120%), live QR code testing modal, and instant animation replay.
- Tests & Deployment: Frontend build compiled cleanly with 0 errors, pushed to origin/main for Vercel deployment.

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
