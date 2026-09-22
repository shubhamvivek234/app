# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v8.0 LinkedIn Outbound & AI Sequence Engine Shipped (Option A Prosp Parity)
Branch: main
Focus: Decoupled Cold Outbound Automation, 1:1 JIT Residential Proxies, Voice Cloning, Unified Inbox

## Last Session Completed
Date: 2026-09-22
Completed:
- Enterprise LinkedIn Cold Outbound Automation Engine (Prosp Option A Architecture):
  - Decoupled `outreach/` backend: Pydantic v2 models, JIT Proxy Manager (Webshare zero-idle cost), AES-256 session cookie encryption.
  - Hybrid Engine: 80% Voyager private REST client + DOM/voice fallback, OutboundRateLimiter with human jitter.
  - Visual Sequence DAG Compiler & Canvas: 10 actions + 4 conditions, Kahn's algorithm cycle detection, prebuilt templates.
  - Lead CRM & Deduplication: CSV ingestion, smart header inference, 4-tier deduplication, blacklist enforcement.
  - ElevenLabs Voice Cloning Pipeline: 30s instant clone, token interpolation (`{{first_name}}`, `{{company_name}}`), dynamic preview synthesis.
  - Multi-Account Unified Inbox: Voyager sync worker, automatic reply detection & CRM sequence cessation, thread reply dispatch.
  - Anti-Ban Safety Shield: 5->10->15->20 warm-up governor, circuit breaker on 403/429/checkpoints, 21-day invite withdrawal.
  - Stripe Billing & Rate Cards: 1-5 ($79.99), 6-30 ($59.99), >30 ($39.99), 4-day trial, auto-release proxy teardown on cancel.
  - Prosp Minimalist UI: Home dashboard, Campaigns, Leads CRM, Unified Inbox, Voice Studio, Settings/Billing, Campaign Wizard.
  - 38/38 outreach unit tests passed, 472/472 full regression tests passed clean, frontend CI build clean.

## Active Work
Currently implementing: None
Next:
- Deploy v8.0 to production.

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
