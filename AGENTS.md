# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-11
Completed:
- Social Graphic Studio Airbnb UI Redesign:
  - Applied Airbnb design language tokens: `#F7F7F7` warm background, `#EBEBEB`/`#DDDDDD` hairlines, `#FF385C` Airbnb Rausch brand voltage, `#222222` ink, and generous rounded radii (`rounded-full` pills, `rounded-3xl` luxury framing).
  - Floating pill switcher for Single Graphic vs LinkedIn Carousel, aspect ratio filter chips, slide itinerary strip, host dashboard inspector tabs, and restyled AI modal.
  - 100% functional fidelity preserved: 12 archetypes, canvas 2D draw engine, multi-page PDF compilation, image download, copy to clipboard, and post composer integration.
  - Verified with 389 backend tests and production frontend build (`npm run build`).

## Active Work
Currently implementing: None
Next:
- Deploy updates to production and verify live health.

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
