# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v5.1 shipped
Branch: main
Focus: Viral Studio Modern & Elegant UI Overhaul (Virlo.ai-inspired Short-Form Intelligence)

## Last Session Completed
Date: 2026-09-02
Completed:
- Viral Studio UI Overhaul (commit `b1cb97d`):
  - Upgraded `/viral-studio` to an agency-grade warm editorial aesthetic matching Unravler's high-end design system.
  - Header & Navigation: Ambient radial dot backdrop, pill eyebrow badge with pulsing amber indicator, display typography, and segmented navigation dock with badge counters.
  - Hook Vault: Crisp hairline search bar with instant clear action, custom niche selector, horizontal category pill strip, and double-bezel card architecture.
  - Virality Gauges & Formula Quotes: Replaced raw emojis with `FaFire` virality chips, styled formula quote containers (`bg-[#F8F8F6]`), and dashed live example cards.
  - AI Video Scriptwriter: Rebuilt with rich brand cards (TikTok, IG Reels, YT Shorts), segmented duration switchers, and vertical timeline beat breakdown (`FaVideo`, `FaFont`, `FaCommentDots`).
  - Teleprompter & Personalize Modal: Dark glass teleprompter viewer with 1-click copy and rounded-3xl generative modal.
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
