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

- Star Button & Particles Integration Shipped & Deployed:
  - Created `star-button.tsx`, `star-button.jsx`, and `demo.tsx` in `frontend/src/components/ui/`.
  - Integrated 6-star cubic-bezier particle hover burst into the "Create New Post" buttons in `DashboardLayout.js` and `Dashboard.js`.
  - Deployed live to production on Vercel (`https://www.unravler.com`, bundle `main.c15f2785.js`).
- Collapsible Sidebar Toggle Arrow Button Shipped & Deployed:
  - Added floating boundary toggle arrow (`FaChevronLeft`/`FaChevronRight`) & bottom menu action in `DashboardLayout.js`.
  - Added `⌘B` / `Ctrl+B` hotkey and `localStorage` persistence (`unravler_sidebar_collapsed`).
- Create Post Account Selection Crash Fix & Campaign Integration:
  - Resolved runtime crash: missing `FaBullhorn` import in `CreatePostForm.js` triggered by active campaigns on account selection.
  - Hardened previews (`TwitterPreview`, `FacebookPreview`, `InstagramPreview`, `LinkedInPreview`) and `PlatformEditor` with safe string guards.
  - Linked Campaigns with Composer: Target channel badges, auto-select matching accounts, query parameter hydration (`?campaign=...`), and "New Post" shortcut in `Campaigns.js`.
  - Added Jest tests (`AccountSelector.test.js`, `Previews.test.js`) & configured Jest `@/*` alias in `craco.config.js`.
- Recurring Post Rule Creation Fix & Instance Spawner Pipeline:
  - Resolved 422 Unprocessable Entity in `POST /api/recurring-rules` (Pydantic required `name` without default, integer `days_of_week` type, and missing `RecurringRuleUpdate` for toggle pause/resume).
  - Connected recurring rules to post templates in `db.posts` (`status="template"`) with initial scheduled instance computation & upcoming counts.
  - Hardened frontend error handling, platform fallback, account mapping, and dark mode UI in `RecurringPosts.js`.
  - Added unit test suite `tests/test_recurring_rules_flow.py` (3/3 passing, 309/309 backend tests passing).
  - Rebuilt and deployed API, worker, beat containers on EC2 and deployed frontend to Vercel (`main.d535c453.js`).
- Master Calendar Default Collapsed in Sidebar Menu:
  - Updated `DashboardLayout.js` so Master Calendar accordion defaults to collapsed (`calendarExpanded = false`), expanding on click.
  - Built and deployed to Vercel production (`main.e2931687.js`).

## Active Work
Currently implementing: None
Next:
- Monitor live user interactions on collapsible sidebar, Create New Post button, and Campaigns Hub.

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
