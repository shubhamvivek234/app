# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v6.9 shipped
Branch: main
Focus: High-Scale Low-Cost Multi-Platform Video Architecture & YouTube Quota

## Last Session Completed
Date: 2026-09-05
Completed:
- Zero-Download Remote Media Probing & Fast-Path (`media.py`, `validation.py`, `storage.py`, `thumbnail.py`): Uses HTTP Range probing to validate 15 GB videos directly in Cloudflare R2; avoids downloading compliant H.264 videos to `/tmp`, eliminating VPS disk crashes (`ENOSPC`).
- Serverless Transcoding Dispatcher (`transcode_dispatcher.py`): Pluggable ephemeral container execution (AWS ECS Fargate / Modal) with local Celery FFmpeg fallback.
- YouTube Quota Tracker & Pacing (`youtube_quota_tracker.py`, `youtube.py`): Daily atomic tracking with midnight-Pacific rollover; prevents 403 quota exhaustion with retry pacing. Created `docs/YOUTUBE_API_QUOTA_GUIDE.md`.
- LinkedIn Video Publishing (`platform_adapters/linkedin.py`): Added native video upload registration (`feedshare-video`) and chunked streaming support.
- Adaptive Pre-Upload Window (`publish.py`): Multi-tiered lookahead (up to 4h) for 15 GB uploads so multi-resolution transcoding finishes before go-live.
- Test Suite: 342/342 backend tests passing (15 new tests); 26/26 Jest tests passing; frontend production build clean.

## Active Work
Currently implementing: None
Next:
- Submit official Google Cloud YouTube Data API quota increase form (1M units/day).

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
