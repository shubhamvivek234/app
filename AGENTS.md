# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v8.0 LinkedIn Outbound & AI Sequence Engine Shipped (Option A Prosp Parity)
Branch: main
Focus: Decoupled Cold Outbound Automation, 1:1 JIT Residential Proxies, Voice Cloning, Unified Inbox

## Last Session Completed
Date: 2026-09-22
Completed:
- Fixed Campaign Wizard View Isolation:
  - Wizard opens as a dedicated full-page screen instead of stacking at the bottom of the Home dashboard.
  - Added Prosp top bar (`← Back`, campaign name input, `Save as template`, `Save and close`, progress bar, `Next: Launch →`).
- Fixed Flowchart Connecting Lines in Sequence Canvas:
  - Built crisp SVG orthogonal connector lines (`#cbd5e1`), vertical trunks, and branch splitters.
  - Implemented condition pills (`✓ accepted` vs `✕ not accepted yet`, `✓ replied` vs `✕ no reply`), centered `+` insertion nodes, `[End]` pills.
  - Added Prosp step inspector right drawers for Voice Note (voice cloner pills, 490 char script, token insertion), InMail, and connection notes.
- 38/38 unit tests pass, frontend CI build clean, pushed to `main` (`9699747`).

## Active Work
Currently implementing: None
Next:
- Verify live Vercel deployment preview with user.

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
