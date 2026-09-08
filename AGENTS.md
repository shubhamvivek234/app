# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-08
Completed:
- Smart Bio Studio Apple Design Alignment & Refinement: Refined `/link-in-bio` Studio (`LinkInBio.js`, `BioOutlineTree.js`, `BioInspectorDrawer.js`, `PublicBioPage.js`, `bioThemeUtils.js`). Replaced Apple branding with official Unravler logo mark in squircle, removed macOS traffic lights dots and "Apple Edition" pill, cleaned up handle pill without copy button box. Added 14 modern, elegant themes (Cosmic Indigo, Natural Titanium, Alpine Pine, Desert Gold, Pure Obsidian, Lavender Silk, etc.). Restored full live responsiveness across Style/Cards/Settings controls (color pickers, blur, radius, spacing, depth, header layout, announcement banner, social dock). Updated published & preview watermarks to "Crafted by Unravler".
- Verification: Frontend production build succeeded (`CI=true npm run build --prefix frontend`) and automated backend test suite passed (`pytest tests/`).

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
