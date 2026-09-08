# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-08
Completed:
- Smart Bio Studio Live Preview Verification & Interactive Controls: Fixed Card Geometry (`sharp` 0px, `squircle` 16px, `pill` 9999px), Card Backdrop Tint (rich calibrated glass tints + solids, hex picker), and Card Text Color (full swatches + hex picker). In `LinkInBio.js`, rendered live-updating sample cards when `activeBlocks.length === 0` so geometry, backdrop tint, and text colors are 100% interactive and visible even on fresh/empty bio pages. Fully synchronized standalone `apple-bio-preview.html` with live DOM-updating controls.
- Verification: Frontend production build succeeded (`CI=true npm run build --prefix frontend`), node utility verification passed, and backend test suite passed (354 passed, 0 failed).

## Active Work
Currently implementing: None
Next:
- Monitor live platform analytics and provider API rate limits across connected social channels.

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
