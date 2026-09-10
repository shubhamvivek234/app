# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-11
Completed:
- Smart Bio Multi-Page Sub-Page Manager Isolation & Dedicated Save Controls:
  - Fixed cross-page block and metadata bleed in `LinkInBio.js` and `BioOutlineTree.js`.
  - Added dedicated Sub-Page Isolated Mode panel with title, description, URL slug, and explicit "Save Page Changes" button.
  - Sub-pages now manage completely isolated block lists while preserving root profile for Home.
  - Updated `PublicBioPage.js` to render isolated sub-page title, badge, description, and document title.
  - Added backend test `test_bio_subpage_isolation_and_save` in `tests/test_bio_pages.py`.
  - Verified with `CI=true npm run build --prefix frontend` (exit 0) and `pytest` (exit 0).

## Active Work
Currently implementing: None
Next:
- Deploy to production and verify live behavior.

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
