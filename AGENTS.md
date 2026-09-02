# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v5.2 shipped
Branch: main
Focus: Social Graphic Studio Modern UI & Multi-Archetype Suite (Postiz & Ray.so-inspired)

## Last Session Completed
Date: 2026-09-02
Completed:
- Social Graphic Studio Modern UI & Feature Expansion (commit `5fe99ea`):
  - Upgraded `/social-graphic-studio` to an agency-grade visual design engine matching Unravler's warm editorial design system.
  - Page Shell & Header: Ambient radial dot backdrop, pill eyebrow badge with pulsing indicator, display typography, and breadcrumbs.
  - 6 Card Archetypes: Modern Glassmorphic, X/Twitter Post Card with verified checkmark & metrics bar, Minimalist Editorial Paper (Georgia serif), Big Stat / KPI Callout with trend pill, macOS Code Terminal (Ray.so style), and 5-Star Testimonial.
  - Customization & Controls: macOS traffic light bar (`🔴 🟡 🟢`), verified checkmark badge toggle, 5-star rating toggle, brand watermark toggle, card shadow depth, and texture overlays (dots, grid, scanlines).
  - Expanded Palettes: 16 curated gradients and 6 solid luxury colors (Jet Black, Slate 900, Pure White, Warm Stone, Racing Green, Royal Navy).
  - AI Carousel & Graphic Generator: Direct integration with `/ai/repurpose` to generate 5-slide carousels or quote copy in 1 click.
  - Interactive Canvas Stage: Aspect ratio switchers (1:1, 4:5, 16:9, 9:16), zoom controls, slide reordering, PDF carousel export, PNG download, and direct "Attach to Post Composer" flow.
- Tests & Deployment: Frontend build verified and 3/3 viral backend tests passed. Pushed to origin/main and synced on EC2.

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
