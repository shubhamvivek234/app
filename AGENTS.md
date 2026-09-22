# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v8.0 LinkedIn Outbound & AI Sequence Engine Shipped (Option A Prosp Parity)
Branch: main
Focus: Decoupled Cold Outbound Automation, 1:1 JIT Residential Proxies, Voice Cloning, Unified Inbox

## Last Session Completed
Date: 2026-09-23
Completed:
- Campaign Auto-Drafting Engine:
  - Added `POST /api/v1/outreach/campaigns/auto-draft` persisting drafts immediately on "+ New campaign" click so work is never lost on refresh or exit.
  - Syncs `draft_step`, `draft_progress`, and `next_step_label` automatically during wizard navigation.
- Dedicated Campaign Detail View (`media_1790104472298.png` – `media_1790104593259.png`):
  - Created `OutreachCampaignDetail.js` with 4 forensic tabs: Analytics (4 KPI cards, Funnel, Audience, Sending from, Schedule, Step & Sender performance), Leads (lead counts, search, ImportLeadsModal), Sequence (empty state with "Open in builder"), and Settings (name, senders, schedule, 8 daily limit pills, "Edit in builder").
  - Clicking any campaign in table opens detail view instead of directly opening wizard.
- Campaigns Hub Parity (`media_1790104399010.png`):
  - Rendered Draft Banner with dynamic progress bar and `[Resume draft]` trigger.
  - Rendered LinkedIn Expert Consultation Banner (`Book a call` with Jack modal).
  - Implemented reversible soft-delete (`DELETE /campaigns/{id}`) with undo alert banner (`POST /campaigns/{id}/restore`).
  - Added Browse Winning Templates view (`media_1790104784825.png`) with one-click sequence adoption.
- 44/44 outreach tests pass, 478/478 repo tests pass, frontend CI clean.

## Active Work
Currently implementing: None
Next:
- Safe audit remediations implemented: Limiter proxy validation, platform coming soon badges, analytics health decoupling, cleanup audit logs, route-level code splitting (-553kB bundle), and GitHub CI workflow.
- Deferred items for later: Firebase key rotation, owner MFA policy, sidebar restructuring, and login/signup variant consolidation.

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
