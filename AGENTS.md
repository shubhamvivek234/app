# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-11
Completed:
- Cluster C & D — Bio Intelligence & Automation Layer:
  - Bio Intelligence: Heatmap density/thermal tiers, conversion funnel analytics, interactive Quick Poll block with real-time voting, NPS / Star rating block with feedback collection, extended Lead Capture (name, phone, custom tags), and A/B Testing traffic split & variant comparison.
  - Automation Layer: Event triggers (`lead.created`, `deal.stage_changed`, `feedback.received`, `broadcast.sent`), actions (`send_email`, `create_deal`, `dispatch_webhook`, `tag_lead`), 5 prebuilt recipe templates, dry-run simulator, and execution audit logs.
  - Dedicated `/automations` frontend hub (3 tabs: My Automations, Recipe Gallery, Execution Logs) with sidebar link.
  - Verified with 389 backend tests (`pytest`) and frontend production build (`npm run build`).

## Active Work
Currently implementing: None
Next:
- Deploy to EC2 production (`ubuntu@51.20.210.184`) and verify live health.

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
