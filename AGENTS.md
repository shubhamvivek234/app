# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v6.6 shipped
Branch: main
Focus: Social Graphic Studio Archetypes & Modern UI Overhaul

## Last Session Completed
Date: 2026-09-04
Completed:
- Social Graphic Studio 12 Archetypes: `glassmorphic`, `bento_glow`, `tweet_card`, `editorial_paper`, `metric_stat`, `brutalist_mono`, `code_snippet`, `testimonial`, `minimal_swiss`, `chat_bubble`, `versus_comparison`, `split_contrast`.
- Card Placement & Sizing: 4 placement modes (Centered, Grounded Bottom, Top Anchored, Edge-to-Edge), 3 width ratios (Compact 78%, Balanced 86%, Wide 94%), live corner radius slider (0-48px).
- Modern 4-Tab Inspector: Layout & Archetype, Canvas & Style, Content & Copy, Archetype Extras with contextual settings (Versus comparison, Chat dialogue, Swiss index, KPI delta, Code lines).
- 12 Curated 1-Click Templates & AI Magic Writer integration.
- Test Suite: 318/318 backend tests passing; 14/14 Jest tests passing; frontend production build clean (`main.5f7a4329.js`).

## Active Work
Currently implementing: None
Next:
- User testing and feedback on visual exports and LinkedIn PDF carousels.

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
