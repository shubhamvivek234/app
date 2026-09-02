# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v5.9 shipped
Branch: main
Focus: Calendar Share Link Modal UI Redesign & QR Code Integration

## Last Session Completed
Date: 2026-09-02
Completed:
- Calendar Share Link Modal UI Redesign (commit `8435410`):
  - Redesigned the share dialog in `CalendarView.js` with `sm:rounded-[28px]`, centered animation, ambient header with pulse indicator, and clean design system tokens.
  - Replaced cramped 1-line layout with a dedicated full-width monospace URL input, 1-click select-all, and prominent copy action with visual checkmark feedback.
  - Added dedicated quick actions: "Open in New Tab" and collapsible "QR Code" generator with mobile scan instructions via `qrcode`.
  - Added permissions & security highlights (Read-Only Access, Private & Secure) and clean separated footer for "Regenerate Token" and "Revoke Link".
  - Verified clean frontend build (`main.0ce208bb.js`), deployed live to Vercel (`main.f50df25d.js`), and synced EC2.

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
