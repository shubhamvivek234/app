# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v8.7 Prosp AI Full Parity Engine & E2E Cold Outreach Shipped
Branch: main
Focus: 7-Source Lead Ingestion, Lead Finder Explorer, Post Engager Scraper, AI Prompt Library, Unified Inbox Tools, CRM Kanban, Analytics Dashboard

## Last Session Completed
Date: 2026-09-23
Completed:
- Forensic Prosp AI Parity (`EU4zSGaPmW0`):
  - 7-Source lead ingestion modal (`source_082s.jpg`) with interactive Lead Finder explorer (10+ multi-criteria filters & live preview table) and Post Engagers scraper (`time_090s.jpg`).
  - AI Prompt Library drawer (`seq_240s.jpg`) pre-seeded with 5 proven outbound prompt architectures, dynamic variable block insertion, and live prospect preview modal.
  - Unified Inbox pro tools (`prosp_inbox_reminders.jpg`, `prosp_inbox_snippets.jpg`, `prosp_inbox_tags.jpg`): Reminders (`⏱ [S]`) with snooze/complete, Snippets drawer (`📋 [C]`) with search & inject, and colored Tags (`🏷 [T]`) with thread filtering.
  - Contacts CRM View Switcher (`prosp_crm_kanban.jpg`): Table (`=`) vs Vertical Stack Kanban (`00`), 5 pipeline columns (`Unassigned`, `In Campaign`, `Contacted`, `Replied`, `Call booked`), drag-and-drop & 1-click stage advancement via `PATCH /leads/{id}/stage`.
  - Campaign & Account Analytics (`prosp_campaign_analytics.jpg`): Dedicated view with 4 KPI summary cards (`Linkedin Requests`, `Messages`, `Engagement`, `Email Delivered`), conversion funnel, and dual-tone daily Sent vs Accepted timeline bar chart.
- 67/67 outreach tests pass, frontend CI clean (`CI=true npm run build`, 807.89 kB gzip main bundle).

## Active Work
Currently implementing: None
Next:
- Sequence pre-warming automation (`LIKE_LAST_POST`, `COMMENT_LAST_POST` in executor).
- Content Writing Styles UI (`OutreachStyles.js`).
- Auto-Plug scheduled first comments in post composer.

## Deploy Notes
- Frontend: Vercel auto-deploys from `main`.
- Backend: EC2 `ubuntu@51.20.210.184` at `/opt/socialentagler`:
  `docker compose --env-file backend/.env -f docker-compose.prod.yml up -d --build`

## Quick Checks
```bash
git status --short
CI=true npm run build --prefix frontend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/test_outreach*.py -q
.venv/bin/python -m compileall api/routes/ai.py utils/free_llm_router.py utils/content_repurposer.py outreach/
```
