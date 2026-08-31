# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v3.7 shipped
Branch: main
Focus: Unravler Smart Bio (Liinks.co-inspired Link-in-Bio Studio, 8 Luxury Themes, Dynamic Social Feed Mirroring, Scheduled Links, Lead Capture, and Click Analytics)

## Last Session Completed
Date: 2026-09-01
Completed:
- Smart Bio Studio & Live Device Simulator (`pages/LinkInBio.js`, `pages/PublicBioPage.js`, `api/routes/bio_pages.py`): Complete block-based editor supporting custom links, badges, visual post feed grids, media embeds, lead capture forms, and markdown quotes with real-time iPhone simulator.
- 8 Curated Agency Themes: Editorial Cream, OLED Vantablack, Electric Indigo, Emerald Forest, Sunset Rose, Obsidian Gold, Nordic Slate, Cyberpunk Neon with customizable typography and button radiuses.
- Analytics & Leads Pipeline: Click & impression tracking (`/track`), top traffic referrers, per-link CTRs, and 1-click CSV audience export (`/leads/export`).
- Tests & Deployment: 279/279 tests passing (100%), frontend production build compiled cleanly, committed to `main` (Vercel), and deployed to EC2 (`{"status":"ok"}`).

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
