# SocialEntangler — Session Memory

> Read first, write last. Keep specific and short.

## Current Phase

Stage: v2.9 complete
Branch: main + version-6
Focus: Content Library scheduled/published card UX follow-up + Cloudflare R2 migration follow-up
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
- Found that production AI routes come from `api/routes/ai.py`, not `backend/server.py`
- Patched the active modular AI route with the same fallback improvements so live `/api/ai/generate-content` and `/api/ai/generate-hashtags` stop returning 503 after Gemini quota failures
- Found the remaining production outage cause: `docker-compose.prod.yml` was not passing AI provider keys into the containers
- Deployed the compose env fix so live `api` now receives `GOOGLE_AI_KEY`, `GROQ_API_KEY`, `COHERE_API_KEY`, `OPENROUTER_API_KEY`, and `EMERGENT_LLM_KEY`
- Verified the live container falls through to OpenRouter successfully; current image is missing `google.generativeai` and `groq`, but OpenRouter free fallback works
- Implemented Published Posts 6-month view retention without deleting post history
- Added dedicated `published_card_thumbnail_url` / `published_media_kind` support to published post responses
- Added publish-time 160x160 WebP published-card thumbnail generation in `celery_workers/tasks/publish.py`
- Added daily cleanup task that deletes only expired published-card thumbnails after 6 months
- Removed the old production-side published-post pruning path that deleted post data beyond the newest 25 items
- Updated `ContentLibrary` published view to use the new card thumbnail/type metadata and replace `All Time` with `Past 6 Months`
- Added focused retention tests in `tests/test_published_post_retention.py`
- Fixed published-post 6-month filtering fallback so published records without `published_at` still appear using `updated_at` / `created_at`
- Extended `ContentLibrary` scheduled view to show thumbnail + post-type badge, fetch all pages, and auto-refresh so published posts leave Scheduled and appear in Published automatically

Files modified:
- `backend/server.py`
- `backend/celery_tasks.py`
- `frontend/src/pages/CreatePostForm.js`
- `frontend/src/components/composer/PlatformEditor.js`
- `frontend/src/lib/mediaValidation.js`

## Active Work

Currently implementing: None
Next concrete step: Commit/push/deploy the scheduled-post Content Library card changes if approved after local review
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
- The modular FastAPI app on EC2 mounts `api/routes/ai.py`; changes in `backend/server.py` do not affect live `/api/ai/*`
- `docker-compose.prod.yml` is a symlink to `docker-compose.yml`; env changes for prod must be made in `docker-compose.yml`
- Current production container image does not have `google.generativeai` or `groq` available at runtime, so OpenRouter is presently the first effective live fallback
- Published Posts page is `frontend/src/pages/ContentLibrary.js` with `status=published`, not `Publish.js`
- Published Posts now use dedicated 160x160 WebP card thumbnails (`published-card-thumbnails/{user_id}/{post_id}.webp`) stored separately from the general media thumbnails
- The new 6-month retention policy applies only to Published Posts card thumbnails and page filtering; post data and analytics history are preserved
- Old production logic in `celery_workers/tasks/publish.py` used to prune published posts beyond 25 items; that call has been removed locally
- `ContentLibrary` now fetches paginated scheduled/published posts in batches of 100 and polls every 30s for status transitions on those views

## Decisions Made This Session

- Remove the DALL-E image-generation block instead of trying to merge it into Common Post
- Keep Common Post as the single shared caption/media source; per-platform panels are derived views with optional overrides
- Block `Post Now` and `Schedule` whenever any selected platform has a Common Post validation error
- Keep unsupported or unconfigured platforms visibly blocked in Common Post instead of silently posting partial payloads
- Show media-required platforms as advisory when they have no media yet; only block once actual uploaded media violates platform rules
- Prefer free/free-tier AI models before paid fallbacks for caption and hashtag generation
- When AI breaks in production, inspect `api/routes/ai.py` and EC2 `api` container logs first, not only `backend/server.py`
- If live AI returns `No AI provider configured`, check compose env passthrough before changing route code again
- Do not reintroduce published-post document deletion for retention; only card-thumbnail cleanup should expire after 6 months

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

Latest run:
- `python3 -m compileall api/routes/ai.py`
- `backend/venv/bin/python` probe calling `_ai_waterfall(...)` from `api/routes/ai.py`
Result: modular app compile passed; active production AI route falls through from Gemini quota failure to Groq with a real response

Latest run:
- EC2 `docker compose exec api` env probe for AI keys
- EC2 `docker compose exec api` probe calling `api.routes.ai._ai_waterfall(...)`
Result: live container now sees all AI keys; Gemini/Groq modules are unavailable in-image, and OpenRouter `openai/gpt-oss-120b:free` returns a valid response

Latest run:
- `python3 -m compileall api/routes/posts.py celery_workers/tasks/publish.py celery_workers/tasks/cleanup.py celery_workers/tasks/scheduler.py api/models/post.py`
- `backend/venv/bin/pytest tests/test_published_post_retention.py -q`
- `CI=true npm run build --prefix frontend`
Result: Python compile passed; 3 retention/media-kind tests passed; frontend production build passed with existing Tailwind/PostHog warnings only

Latest run:
- `CI=true npm run build --prefix frontend`
Result: frontend production build passed after the scheduled-post card updates; only existing Tailwind/PostHog warnings remain

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
