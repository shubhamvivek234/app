# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Deep Codebase & Architecture Audit Remediation (Payments, Adapters, Media, Workspaces)

## Last Session Completed
Date: 2026-09-11
Completed:
- Cluster B — Monetization Engine & Broadcast Lite:
  - Added Smart Bio `payment_link` block with amount, currency, gateway selector (Razorpay, UPI, PayPal, Stripe/Custom).
  - Implemented `/api/bio-pages/payment-link` generator endpoint.
  - Implemented `/api/broadcasts` router: campaign CRUD, stats, SES/Resend async dispatches, test emails.
  - Catalog of 6 responsive email templates (`api/data/email_templates.py`).
  - Added `/api/ai/broadcast-draft` copywriter endpoint with fallback generator.
  - Added `/api/broadcasts/whatsapp-links` personalized `wa.me` outreach pipeline.
  - Added dedicated `/broadcast` frontend hub with 4 tabs and integrated sidebar navigation.
  - Verified with 380 backend tests (`pytest`) and frontend production build (`npm run build`).

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
