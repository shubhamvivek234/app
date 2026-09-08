# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-09
Completed:
- Smart Bio Scheduled Visibility Window: Added optional `page_schedule` (`enabled`, `start_at`, `end_at`) to bio backend and frontend. Pages outside window safely return 404 with friendly Apple-styled "Coming Soon" or "Page Expired" status cards. Studio top header shows live schedule status pill.
- Smart Bio Permanent Deletion: Added `DELETE /bio-pages/mine` and `DELETE /bio/me` to erase MongoDB page record, release handle, and wipe analytics & leads. Implemented Apple-styled confirmation modal requiring handle typing before permanent deletion.
- Verification: Frontend production build (`CI=true npm run build --prefix frontend`) passed (exit code 0); 358 backend unit tests passed (including new schedule & deletion tests).

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
