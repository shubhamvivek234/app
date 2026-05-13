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
- Fixed Common Post empty-state validation so media-required platforms now show guidance, not blocking errors, until media is actually added
- Re-enabled direct media upload/removal/reorder inside each selected platform panel
- Fixed submit gating so platform-only media overrides count as real post content
- Hardened AI content/hashtag waterfall to use real provider fallbacks instead of the mocked local Emergent fallback
- Prioritized free/free-tier models in the AI chain: Gemini free tier, Groq LLaMA 3.3, and multiple OpenRouter free models
- Improved hashtag generator error handling to surface backend failure details in the UI

Files modified:
- `backend/server.py`
- `backend/celery_tasks.py`
- `frontend/src/pages/CreatePostForm.js`
- `frontend/src/components/composer/PlatformEditor.js`
- `frontend/src/lib/mediaValidation.js`

## Active Work

Currently implementing: AI assistant + hashtag generator reliability fix
Next concrete step: Deploy backend/frontend and verify Create Post AI + Hashtag Generator against live env
Blocked on: some platform publishers are still not fully configured (`threads`, `bluesky`, `pinterest`) and Common Post marks them unsupported

## Architecture Notes

- `Common Post` is now the shared source layer in `CreatePostForm`; untouched platform panels derive caption/media from it
- Per-platform edits create overrides instead of mutating shared content; `Reset to Common` clears those overrides
- `platform_overrides` now persists through `backend/server.py` and is read by `backend/celery_tasks.py` during publish
- Current Common Post validation is aligned to what this workspace can actually publish today, not to theoretical platform limits
- Empty Common Post media is no longer treated as an immediate error for Instagram/YouTube/TikTok; only actual uploaded-media incompatibilities block submit
- Selected platform panels can upload their own media overrides even when Common Post media is empty
- AI generation now falls through across configured providers on general provider failure, not just rate limits
- The local `backend/emergentintegrations` package is a mock; do not treat it as a real production LLM fallback

## Decisions Made This Session

- Remove the DALL-E image-generation block instead of trying to merge it into Common Post
- Keep Common Post as the single shared caption/media source; per-platform panels are derived views with optional overrides
- Block `Post Now` and `Schedule` whenever any selected platform has a Common Post validation error
- Keep unsupported or unconfigured platforms visibly blocked in Common Post instead of silently posting partial payloads
- Show media-required platforms as advisory when they have no media yet; only block once actual uploaded media violates platform rules
- Prefer free/free-tier AI models before paid fallbacks for caption and hashtag generation

## Test Status

Last run:
- `python3 -m compileall backend/server.py backend/celery_tasks.py`
- `CI=true npm run build`
Result: backend compile passed; frontend production build passed with existing warnings only

Latest run:
- `CI=true npm run build --prefix frontend`
Result: passed with existing Tailwind/PostHog warnings only

Latest run:
- `python3 -m compileall backend/server.py`
- `venv/bin/python` probe calling `_ai_waterfall(...)` from `backend/server.py`
Result: backend compile passed; Gemini hit quota and fell through successfully to Groq with a real response

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
- Do not touch unrelated `frontend/.gitignore`, `.vercelignore`, or `.playwright-mcp/` changes unless explicitly asked
- `threads`, `bluesky`, and `pinterest` are intentionally blocked in Common Post because publish adapters are not ready
- Secrets previously shown in chat should be treated as compromised until rotated
- `frontend/.vercel/project.json` points to the wrong Vercel project locally; deploy the live frontend from repo root linked to `app-fgv2`
