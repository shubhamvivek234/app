# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v3.2 shipped
Branch: main
Focus: 6-Tier Free LLM Waterfall & Minimalist Inbound Suite (Universal Repurposer, Voice-to-Post PostCast, Content DNA Voice Profiler, Multi-Page PDF Carousel Studio, AI Smart Replies)

## Last Session Completed
Date: 2026-08-30
Completed:
- 6-Tier Free LLM Waterfall Router (`utils/free_llm_router.py`): Zero-cost cascade across Google Gemini 2.5 Flash, Groq GPT-OSS 120B/20B, OpenRouter Free Pool, and Cohere Command R with automatic rate-limit failover.
- Universal Repurposer (`utils/content_repurposer.py`, `POST /ai/repurpose`): Extracts YouTube transcripts, article URLs, and notes into multi-network social draft packages.
- Voice-to-Post "PostCast" (`POST /ai/voice-to-post`): Ingests raw audio recordings, strips disfluencies, and generates structured social posts.
- Content DNA Profiler (`POST /ai/content-dna/scan`, `BrandVoiceSettings.js`): 1-click writing style extraction analyzing recent posts without manual form filling.
- LinkedIn PDF Carousel Studio (`SocialGraphicStudio.js`): Multi-slide carousel mode with 1-click multi-page vector PDF export via `jspdf`.
- AI Smart Reply Suggestions (`Inbox.js`, `POST /ai/suggest-comment`): Contextual value-add reply suggestions.
- Tests & Deployment: 265/265 tests passed (100%), frontend production build compiled and deployed to Vercel (`https://www.unravler.com/`).

## Active Work
Currently implementing: None
Next:
- Implement legal & app verification roadmap (`docs/APP_VERIFICATION_AND_LEGAL_PLAN.md`) when business details are provided.
- Finish Cloudflare R2 migration (direct-to-R2 presigned uploads) and eliminate any remaining local-disk media paths.

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
