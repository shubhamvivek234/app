# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v8.0 LinkedIn Outbound & AI Sequence Engine Shipped (Option A Prosp Parity)
Branch: main
Focus: Decoupled Cold Outbound Automation, 1:1 JIT Residential Proxies, Voice Cloning, Unified Inbox

## Last Session Completed
Date: 2026-09-23
Completed:
- Locked right-side drawer to fixed viewport height (`h-full max-h-full overflow-hidden`) so it never stretches vertically when sequence canvas expands (`0681559`).
- Shipped pixel-perfect Prosp parity for Wizard Step 3 (Launch & Senders) per `media_1790103490135.png`:
  - Campaign name card, multi-sender account picker with `Select all` / `Clear`.
  - Weekly hours schedule editor (S-M-T-W-T-F-S) with inline time ranges, copy-to-all weekdays, timezone selector.
  - Daily limits per sender with safe defaults badge and 8 item counters (`[-] [ 20 ] [+]`).
  - Full-width `Review and launch →` action.
- Pixel-matched Leads CRM (`media_1790103640399.png`) and Inbox empty states/account cards (`media_1790103710555.png`).
- 38/38 unit tests pass, frontend CI build clean, deployed to `main` (`8d4fb36`), EC2 synced.

## Active Work
Currently implementing: None
Next:
- Verify live preview and campaign run with user.

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
