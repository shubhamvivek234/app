# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v5.8 shipped
Branch: main
Focus: Header Action Icons (Theme & Notification) Alignment Harmonization

## Last Session Completed
Date: 2026-09-02
Completed:
- Header Theme & Notification Icons Alignment (commit `8ba4d2f`):
  - Standardized both Theme toggle and Notification Center buttons into identical `w-9 h-9 flex items-center justify-center rounded-xl` containers.
  - Aligned icon centers horizontally and vertically along the same 18px centerline (theme icon scaled to 16px, BellRingIcon to 18px).
  - Repositioned the unread badge to `-top-0.5 -right-0.5` and dropdown trigger to `top-full mt-2.5` to match `UserMenu`.
  - Verified clean frontend build (`main.b8b9f485.js`), deployed live to Vercel (`main.4a6c96b0.js`), and synced EC2.

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
