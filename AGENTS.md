# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v3.9 shipped
Branch: main
Focus: Smart Bio Studio Tactile Physical UI & Procedural Backdrop Engine (18 Curated Designer Themes, 8 Tactile 3D Card Physics, Procedural SVG Film Grain & Ambient Defocused Orbs, 4 Header Architectures, Priority CTA Attention Pulse)

## Last Session Completed
Date: 2026-09-01
Completed:
- Smart Bio Studio Theme & Tactile Engine (`frontend/src/lib/bioThemeUtils.js`, `pages/LinkInBio.js`, `pages/PublicBioPage.js`, `api/models/bio.py`, `api/routes/bio_pages.py`):
  - 18 Curated Designer Themes across dark OLED, luxury editorial washi, warm terracotta, emerald glass, neon cyberpunk, and liquid aura.
  - 8 Tactile 3D Card Styles (Double-Bezel Glass, Tactile Convex 3D, Tactile Concave Inset, Hard Brutalist, Cyber Glow Halo, Soft Marshmallow Pill, Minimal Hairline, Solid Flat).
  - Procedural Background Effects (SVG Film Grain Noise overlay, Ambient Defocused Light Orbs, Liquid Multi-stop Mesh Glow).
  - 4 Header Architectures (Classic Centered, Banner Cover Photo, Editorial Horizontal Split, Minimalist Monograph).
- Sidebar Menu & Navigation Refactor (`DashboardLayout.js`): Removed redundant Short Links item from main sidebar (centralized inside Social Tools hub).
- Dark Theme Overhaul for Publish & Analytics (`DashboardLayout.js`, `Publish.js`, `PostCard.js`, `ExportReportModal.js`, `index.css`):
  - Top header navigation Publish & Analytics links upgraded with high-contrast dark pills and smooth React Router client-side routing.
  - Full dark theme styling across Publish feed, account pills, post cards, comments drawer, DM inbox, Analytics cards, and PDF export modal.
- Tests & Deployment: 282/282 tests passing (100%), frontend production build compiled cleanly, committed to `main` (Vercel), and deployed to EC2.

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
