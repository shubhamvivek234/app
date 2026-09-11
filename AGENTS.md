# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-11
Completed:
- Canva OAuth & Modal Remediation:
  - Fixed blank screen upon Canva OAuth redirect (`/api/media-sources/canva/callback`) by redirecting directly to `{frontend_base}/oauth/callback` with multi-channel cross-tab syncing (`BroadcastChannel`, `localStorage`, `postMessage`).
  - Fixed infinite loading loop in `PlatformEditor.js` when connected Canva account has 0 designs by introducing a `canvaLoaded` guard.
  - Added empty state card with Canva direct link ("Create Design on Canva") and Refresh button.
  - Sanitized Canva designs API params (`limit`, `query`, `continuation`) and robust timestamp parsing.
  - Verified with 7 passing tests in `tests/test_media_sources_route.py` and clean frontend production build.

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
