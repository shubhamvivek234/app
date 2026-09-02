# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v5.3 shipped
Branch: main
Focus: Full Deployment Verification & Smart Bio Block Image Visibility Fix

## Last Session Completed
Date: 2026-09-02
Completed:
- Smart Bio Block Editor Image Visibility Fix (commit `24cb35f`):
  - Solved image preview issues in `BioBlockEditorModal.js` by adding `normalizeImageUrl` to clean whitespace and auto-convert Google Drive (`drive.google.com/file/d/`), Dropbox (`dropbox.com`), and Imgur sharing links to direct thumbnail/image links.
  - Added direct local image file upload (`FileReader` via `<input type="file" />`) so users can load any image file from their device without needing a public URL.
  - Added real-time image error detection (`imageError`) with a clear advisory alert if an image URL fails to load.
  - Added 6 curated royalty-free image presets and interactive pickers for Icon, Emoji, and 3D Art tabs.
  - Upgraded live Card Preview to accurately render all layout archetypes (`card_banner_top`, `card_left_image`, `compact_pill`) and media fallbacks.
  - Added `onError` fallback handlers in `BioOutlineTree.js` and `LinkInBio.js` canvas to prevent broken browser image icons.
- Full 3-Hour Deployment Verification:
  - Verified and deployed commits `b1cb97d` (Viral Studio overhaul), `5fe99ea` (Social Graphic Studio multi-archetypes & AI carousel), and `24cb35f` (Smart Bio image fixes).
  - Promoted and aliased production build (`main.fab4fed6.js`) to `https://www.unravler.com`.
  - EC2 backend synchronized at commit `24cb35f` with 100% healthy services.

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
