# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v6.5 shipped
Branch: main
Focus: Postpeer Capabilities (P1–P4) — MCP Server, Failure Diagnostics & Retry, Webhooks, Google Business Profile

## Last Session Completed
Date: 2026-09-04
Completed:
- P1 (Unravler MCP Server for AI Agents): Public API `/campaigns` and `/calendar`, MCP tools `campaigns.list`, `campaigns.get`, `calendar.get` (19 total tools), interactive client tabs (Cursor, Claude, Windsurf) in `Developers.js`.
- P2 ("Retry Failed Platforms Only" + Granular Error Diagnostics): `publishFailures.js` error parser (Meta, X, LinkedIn, YouTube, TikTok), `PostDeliveryInspector.js` with isolated platform retries & error banners, integrated into `ContentLibrary.js`, `DayAgendaPanel.js`, `CalendarView.js`, `Campaigns.js`, with notification deep linking (`highlightPost`).
- P3 (Webhook Triggers Suite): `post.partial_failed` webhook event, enriched diagnostic payloads with `failed_platforms`, 1-click Slack/Discord/Zapier quick presets in `Developers.js`.
- P4 (Google Business Profile Integration): `GoogleBusinessAdapter` with Call-To-Action buttons, photo attachments, direct connect `/social-accounts/google-business/connect` + OAuth, Composer CTA controls in `PlatformEditor.js` & `CreatePostForm.js`, badge chips in `CalendarPostChip.js`, `ContentLibrary.js`, `ConnectedAccounts.js`.
- Test Suite: 5/5 passing in `tests/test_p1_p4_features.py`; 318/318 backend tests passing; 14/14 Jest tests passing; frontend production build clean (`main.f18d7934.js`).

## Active Work
Currently implementing: None
Next:
- Monitor live MCP server and Google Business Profile usage.

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
