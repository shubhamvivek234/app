# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-08
Completed:
- Smart Bio Studio Apple Design System Overhaul: Redesigned `/link-in-bio` Studio (`LinkInBio.js`, `BioOutlineTree.js`, `BioInspectorDrawer.js`, `BioBlockEditorModal.js`) with Apple macOS Sequoia and iOS 18 design language. Features floating frosted top bar with window controls, Apple capsule device switcher (`Mobile`, `Tablet`, `Desktop`), titanium iPhone 16 Pro chassis with Dynamic Island, tactile side buttons, macOS sheets, squircle cards, and dark/light mode parity while maintaining 100% of existing functionality and data contracts.
- Verification: Frontend production build succeeded (`CI=true npm run build --prefix frontend`) and all 354 backend tests passed (`pytest tests/`).

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
