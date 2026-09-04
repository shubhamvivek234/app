# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v6.7 shipped
Branch: main
Focus: Unified Smart Media Preflight & Auto-Optimization Engine

## Last Session Completed
Date: 2026-09-04
Completed:
- Canonical Platform Specs (`media_pipeline/platform_specs.py`): Single source of truth for 10 platforms, eliminating rule drift across frontend, upload validator, and worker pipeline.
- Smart Media Transformations (`media_pipeline/ffmpeg_worker.py` & `media_pipeline/image_worker.py`):
  * Vertical 9:16 auto-fit (`blur_pad` blurred Gaussian background padding or `center_crop`) for TikTok, Reels, Shorts.
  * Smart auto-compression for video (computed target bitrate) and images (iterative Pillow compression).
  * Auto silent audio track injection (`anullsrc`) for platforms requiring audio streams.
- Transformation API Endpoints (`api/routes/upload.py`): `auto-fit-vertical`, `auto-compress`, and `add-silent-audio`.
- Post Composer 1-Click Fixes (`PlatformEditor.js`, `CreatePostForm.js`, `mediaValidation.js`): Interactive 1-click action buttons on validation errors, warnings, and media thumbnails.
- Test Suite: 327/327 backend tests passing; 19/19 Jest tests passing; frontend production build clean (`main.2617a123.js`).

## Active Work
Currently implementing: None
Next:
- Real-world validation with end-user uploads and social platform publishing.

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
