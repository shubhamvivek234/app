# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-08
Completed:
- Smart Bio Studio Apple Design Alignment: Refined `/link-in-bio` Studio (`LinkInBio.js`, `BioOutlineTree.js`, `BioInspectorDrawer.js`, `index.css`) to match the approved Apple preview (`apple_bio_studio_preview.html`). Features pixel-perfect titanium iPhone 16 Pro chassis with authentic specular hairline shadow, Dynamic Island with blue ping & sensors, ambient radial mesh blur, 3-tab Apple Studio Inspector (`Style`, `Cards`, `Settings`) with visual gradient preset cards and sliders, live workspace bio & direct identity inputs, and full dark/light theme parity.
- Verification: Frontend production build succeeded (`CI=true npm run build --prefix frontend`) and automated backend tests passed (`pytest tests/`).

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
