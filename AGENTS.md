# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v4.5 shipped
Branch: main
Focus: Smart Bio Live Preview Color/Style Binding & Robust Backend Publishing Verification

## Last Session Completed
Date: 2026-09-02
Completed:
- Smart Bio Real-Time Color & Style Binding (`frontend/src/components/bio/BioInspectorDrawer.js`, `frontend/src/pages/LinkInBio.js`, `frontend/src/pages/PublicBioPage.js`):
  - Added full color customizer: card background color with opacity presets, card border color, card text color, background gradient presets, brand accent swatches.
  - Added tactile card style archetype picker (Double-Bezel Glass, Convex 3D, Concave Inset, Neobrutalist, Cyber Glow, Soft Pill, Minimal Hairline, Solid Flat).
  - Wired live preview and public page to immediately reflect card background, border, text color, corner radius %, and shadow depth.
- Smart Bio Backend & Publishing Resilience (`api/routes/bio_pages.py`, `frontend/src/pages/LinkInBio.js`):
  - Relaxed Pydantic validation (`extra="allow"`) across all models, preventing 422 errors on custom styling properties.
  - Auto-sanitized URLs with `https://` prefix fallback and robust fallback for handle/title.
- Tests & Deployment: 282/282 tests passing (100%), frontend production build compiled cleanly with 0 errors, pushed to origin/main for Vercel and EC2 deployment.

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
