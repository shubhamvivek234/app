# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-09
Completed:
- Smart Bio Scheduled Visibility Window & Modal: Added optional `page_schedule` (`enabled`, `start_at`, `end_at`) to bio backend and frontend. Added prominent `[ 🕒 Schedule ]` button in Studio top bar, made top status badge clickable, and created Apple-styled `BioScheduleModal.js` with 1-click presets (24h, 3d, 7d) and live status preview.
- Smart Bio Header Size Slider: Added slide bar directly under Header Layout choices in Styles tab (48px to 140px with Compact, Standard, Hero presets) with proportional avatar and typography scaling in studio & public view.
- Smart Bio Analytics Modal Overhaul: Redesigned with Double-Bezel Apple architecture, segmented tabs (Overview, Top Links, Traffic Sources), 7-day trend bars, hardware split, and Esc / backdrop dismissal.
- Verification: Frontend production build passed (exit code 0); 356 pytest unit tests passed.

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
