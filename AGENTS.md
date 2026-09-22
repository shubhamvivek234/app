# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v8.0 LinkedIn Outbound & AI Sequence Engine Shipped (Option A Prosp Parity)
Branch: main
Focus: Decoupled Cold Outbound Automation, 1:1 JIT Residential Proxies, Voice Cloning, Unified Inbox

## Last Session Completed
Date: 2026-09-22
Completed:
- Shipped Dynamic Recursive Sequence Tree Engine (Prosp Parity):
  - Full recursive hierarchy matching screenshots (`media_1790088300707.png`, `media_1790088397090.png`, `media_1790088446398.png`).
  - Condition nodes (`If connected` -> `✕ not connected` vs `✓ connected`) with amber chain styling.
  - Inline card header delay editor (`🕒 [ 4 ] [ days ▾ ] [ ✓ ]`).
  - Card context menu (`⋮` -> `Edit step`, `Delete step`).
  - Dynamic step/condition insertion at any `+` point, live toast banners, and right drawer inspector.
- 38/38 unit tests pass, frontend CI build clean, pushed to `main` (`2c2d52a`).

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
