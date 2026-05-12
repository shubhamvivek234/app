# SocialEntangler — Session Memory

> Read first, write last. Keep specific and short.

## Current Phase

Stage: v2.9 complete
Branch: main + version-6
Focus: Create Post Common Post composer + Cloudflare R2 migration follow-up
Arch refs: Architecture v2.9 / Implementation Plan v3.0

## Last Session Completed

Date: 2026-05-13
Completed tasks:
- Removed the `Generate image with AI (DALL-E 3)` block from `CreatePostForm`
- Added `Common Post` as the shared source for caption + media in Create Post
- Added platform-level Common Post validation with persistent blocking errors and submit disable
- Added platform-specific reset-to-common and per-platform crop override flow on top of shared media
- Persisted `platform_overrides`, `media_types`, `youtube_privacy`, and TikTok options through `/api/posts`
- Updated Celery publish path to honor per-platform content/media overrides and clean up override media URLs

Files modified:
- `backend/server.py`
- `backend/celery_tasks.py`
- `frontend/src/pages/CreatePostForm.js`
- `frontend/src/components/composer/PlatformEditor.js`
- `frontend/src/lib/mediaValidation.js`

## Active Work

Currently implementing: Common Post shipped in Create Post UI + backend payload path
Next concrete step: Live browser verification for multi-platform Common Post, especially crop/error flows and real publish behavior per platform
Blocked on: some platform publishers are still not fully configured (`threads`, `bluesky`, `pinterest`) and Common Post marks them unsupported

## Architecture Notes

- `Common Post` is now the shared source layer in `CreatePostForm`; untouched platform panels derive caption/media from it
- Per-platform edits create overrides instead of mutating shared content; `Reset to Common` clears those overrides
- `platform_overrides` now persists through `backend/server.py` and is read by `backend/celery_tasks.py` during publish
- Current Common Post validation is aligned to what this workspace can actually publish today, not to theoretical platform limits

## Decisions Made This Session

- Remove the DALL-E image-generation block instead of trying to merge it into Common Post
- Keep Common Post as the single shared caption/media source; per-platform panels are derived views with optional overrides
- Block `Post Now` and `Schedule` whenever any selected platform has a Common Post validation error
- Keep unsupported or unconfigured platforms visibly blocked in Common Post instead of silently posting partial payloads

## Test Status

Last run:
- `python3 -m compileall backend/server.py backend/celery_tasks.py`
- `CI=true npm run build`
Result: backend compile passed; frontend production build passed with existing warnings only

## Notes for Next Session

Start with:
```bash
cat AGENTS.md
git status --short
git log --oneline -5
CI=true npm run build --prefix frontend
python3 -m compileall backend/server.py backend/celery_tasks.py
```

Important:
- Do not touch unrelated `.claude/worktrees/*` changes
- `threads`, `bluesky`, and `pinterest` are intentionally blocked in Common Post because publish adapters are not ready
- Secrets previously shown in chat should be treated as compromised until rotated
