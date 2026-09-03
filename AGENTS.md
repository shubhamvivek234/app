# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v6.0 shipped
Branch: main
Focus: Analytics & Reports Overhaul — Real Metrics, CSV Export, Pop-up Free PDF, Dark Theme UI

## Last Session Completed
Date: 2026-09-04
Completed:
- Enterprise Features & Campaigns Hub (Phases 1-3 Shipped & Verified):
  - Phase 1: Workspace Approval Governance (`api/routes/team.py`, `api/routes/posts.py`, `Settings.js`), Universal First Comment Execution (`celery_workers/tasks/publish.py`), AI Remix for Evergreen Posts (`api/routes/recurring.py`, `celery_workers/tasks/recurring.py`, `RecurringPosts.js`).
  - Phase 2: Pre-Publish Video & Media Validator (`CreatePostForm.js`, `mediaInspector.js`), Multi-Profile Brand Kit with Signature CTA (`api/routes/ai.py`, `BrandVoiceSettings.js`), RSS Autopilot with AI Hook Generation (`api/routes/rss_feeds.py`).
  - Phase 3: Dedicated Campaigns Hub (`api/routes/campaigns.py`, `Campaigns.js`, `App.js`, `DashboardLayout.js`, `CreatePostForm.js`), Social Inbox Lead Tagging & CRM Lite (`api/routes/inbox.py`, `Inbox.js`), Thread Splitter Utility (`utils/thread_splitter.py`).
  - Test Suite: 9/9 new tests passing in `tests/test_phase1_postly_features.py`; all 306 backend tests passing; frontend build clean (`main.a3c1ef9f.js`).

## Active Work
Currently implementing: Deployment & Verification
Next:
- Deploy to EC2 production backend and verify live endpoints.

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
