# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v4.2 shipped
Branch: main
Focus: Direct Full-Page Create Post Composer + Universal Smart Media Engine & Real-Time Multi-Platform Rules

## Last Session Completed
Date: 2026-09-02
Completed:
- Direct Full-Page Create Post Composer (`frontend/src/pages/CreatePost.js`, `frontend/src/pages/CreatePostForm.js`):
  - Removed intermediate 4-card landing screen (`Text Post`, `Image Post`, `Video Post`, `Mixed Media`).
  - Replaced 88vw×88vh popup modal with direct full-page composer in `DashboardLayout`.
- Universal Smart Media Engine (`frontend/src/components/composer/PlatformEditor.js`, `frontend/src/lib/mediaValidation.js`):
  - Universal smart dropzone accepting all media types (`image/*`, `video/*`, `.gif`, `.pdf`, `.mp3`, `.wav`) simultaneously.
  - Multi-file drag-and-drop, PDF document preview tiles, video audio indicators, and real-time classification (`single_image`, `carousel_images`, `single_video`, `vertical_reel`, `pdf_document`, `mixed_media`).
  - Verified platform limits for Instagram (10 carousel items), Facebook (10+ photos), Twitter/X (4 images / 1 video), LinkedIn (9 images / PDF documents), YouTube (1 video / Shorts), TikTok (1 video / 35 photos).
- Tests & Deployment: 282/282 tests passing (100%), frontend production build compiled with 0 errors, EC2 healthy.

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
