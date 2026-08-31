# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v3.8 shipped
Branch: main
Focus: Viral Hook Vault (880+ Battle-Tested Short-Form Hooks across 12 Archetypes and 8 Niches), AI Short-Form Video Storyboard Studio (TikTok, Reels, Shorts), and Post Composer 1-Click Hook Injector

## Last Session Completed
Date: 2026-09-01
Completed:
- Viral Hook Vault (`api/data/viral_hooks_catalog.py`, `pages/ViralStudio.js`, `api/routes/ai.py`): 880+ structured short-form viral hooks categorized across 12 psychological triggers and 8 creator niches with instant search, 1-click personalizer, infinite pagination, and bookmarks.
- AI Video Storyboard Studio: Generates 3 hook variations, 30-45s timed visual storyboards (camera cues, on-screen text, spoken dialogue), teleprompter transcripts, and 1-click "Schedule in Composer" handoff.
- Post Composer Integration (`pages/CreatePostForm.js`): Added "⚡ Viral Hooks" dialog inside post creation interface for instant hook injection into drafts.
- Tests & Deployment: 282/282 tests passing (100%), frontend production build compiled cleanly, committed to `main` (Vercel), and deployed to EC2 (`{"status":"ok"}`).

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
