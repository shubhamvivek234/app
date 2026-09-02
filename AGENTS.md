# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v5.0 shipped
Branch: main
Focus: Smart Bio Studio Light Theme Redesign (liinks.co inspired)

## Last Session Completed
Date: 2026-09-02
Completed:
- Smart Bio Studio Light Theme Redesign (commit `7a19c4f`):
  - Converted entire Smart Bio Studio from dark moody zinc theme to clean warm light editorial aesthetic.
  - 4 files changed, 308 insertions, 308 deletions (CSS-only, zero functionality changes).
  - `LinkInBio.js`: White header bar (`bg-white/95`), warm canvas (`bg-[#F0F0EE]`), light dot grid, blue publish CTA, clean device switcher, light modals.
  - `BioOutlineTree.js`: White panel bg, `gray-50` accordion sections, clean `gray-200` borders, light inputs and action buttons.
  - `BioInspectorDrawer.js`: White inspector bg, clean category rows, `gray-50` controls, `blue-500` accent states, light sliders.
  - `BioBlockEditorModal.js`: White modal bg, light form inputs, clean layout selectors.
  - Reference: liinks.co screenshots in artifacts directory.
- Tests & Deployment: Frontend build and 282 backend tests passed cleanly. Pushed to origin/main and synced on EC2.

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
