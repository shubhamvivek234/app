# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v4.6 shipped
Branch: main
Focus: Studio Spacing, Device Frame Containment, Reactive Swatches, & Email Verification Isolation

## Last Session Completed
Date: 2026-09-02
Completed:
- Studio Spacing & Device Viewport Containment (`frontend/src/pages/LinkInBio.js`):
  - Passed `noPadding={true}` to `DashboardLayout`, removing 24px gap above the studio header.
  - Integrated device switcher pills directly into the top studio header bar.
  - Added responsive max-width bounds and overflow containment for tablet/desktop preview devices.
- Reactive Card Background Swatches & Publishing (`frontend/src/components/bio/BioInspectorDrawer.js`, `frontend/src/pages/LinkInBio.js`):
  - Added `rgbaToHex` conversion and 10 instant palette swatches.
  - Publishing automatically opens the live published bio in a new browser tab.
- Email Verification Banner Isolation (`frontend/src/App.js`):
  - Removed top-level `EmailVerificationBanner` so email verification notices only appear in Dashboard Action Center and Settings.
- Tests & Deployment: Frontend build compiled cleanly with 0 errors, pushed to origin/main and deployed to EC2.

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
