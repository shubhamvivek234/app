# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v8.0 LinkedIn Outbound & AI Sequence Engine Shipped (Option A Prosp Parity)
Branch: main
Focus: Decoupled Cold Outbound Automation, 1:1 JIT Residential Proxies, Voice Cloning, Unified Inbox

## Last Session Completed
Date: 2026-09-23
Completed:
- Unified Inbox Forensic Parity (`media_1790103710555.png`):
  - Two-pane split layout: Left thread panel (`w-[380px]`) & Right thread detail / empty state.
  - Rendered `[ Prosp | All ]` segmented pill toggle with default on `All`.
  - Added rounded search input `Search conversations`.
  - Implemented Accounts Dropdown with open state showing `All accounts` and *"No connected accounts. Connect one in Settings to see conversations."* notice when empty, or sender account switcher.
  - Centered left empty state: *"No conversations yet."*.
  - Centered right empty state: Lavender rounded-2xl icon box + *"Select a conversation / Choose a thread from the list to read the conversation and reply."*.
  - Full chat thread view with inbound/outbound bubbles, voice note player, AI quick-replies, and Voyager message reply dispatch.
- Backend Inbox Engine:
  - Multi-field user filter `{"$or": [{"user_id": user_id}, {"workspace_id": user_id}]}` on threads and replies.
  - Added `source` filter (`outreach` vs `all`) and `POST /inbox/{id}/ai-reply` suggestions endpoint.
- 53/53 outreach tests pass, 482/482 repo tests pass, frontend CI clean.

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
