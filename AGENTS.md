# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-20
Completed:
- Add Audio to Video Audit & End-to-End Implementation:
  - Fixed button collisions between Audio and Auto-Fit in Composer (`PlatformEditor.js`).
  - Added 6 curated royalty-free music tracks with pre-computed waveforms (`api/data/stock_audio.py`, `frontend/src/data/stockAudio.json`).
  - Upgraded `AddAudioDialog.js`: interactive waveform scrubber, synchronized audio-video playback, volume balance sliders, and temporary upload library persistence.
  - Integrated audio in Media Library (`MediaLibrary.js`): audio filter tab, direct upload, inline preview card, and one-click "Add Audio" action on videos.
  - Dynamic audio attribution tags in TikTok and Instagram previews.
  - All automated media/audio tests and frontend production build verified clean.

## Active Work
Currently implementing: None
Next:
- Deploy updates to production.

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
