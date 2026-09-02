# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v5.5 shipped
Branch: main
Focus: Calendar Share Link Generation, Revocation & Public Calendar View

## Last Session Completed
Date: 2026-09-02
Completed:
- Calendar Grid Share Link Fix & Public Calendar View (commit `9e209b4`):
  - Fixed share link generation (`POST /calendar/share`) by allowing omitted/default body and reusing active unexpired workspace tokens unless `regenerate: true`.
  - Implemented `GET /calendar/share` and `DELETE /calendar/share` to check active links and support 1-click token revocation.
  - Implemented public view endpoint `GET /calendar/public/{token}` returning non-deleted scheduled/published posts, calendar notes, and workspace branding with expiry verification.
  - Upgraded share modal in `CalendarView.js` with direct "Open in New Tab", visual "Copied" feedback, "Regenerate link", and "Revoke link" actions.
  - Rebuilt `PublicCalendar.js` into an agency-grade, read-only responsive calendar with month navigation, day cells, post cards, and interactive post inspection dialog.
  - Verified 9/9 pytest unit tests in `test_calendar_notes.py` and clean frontend build (`main.768d50b2.js`).
  - Deployed live to production on Vercel (`https://www.unravler.com`) and updated EC2 container.

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
