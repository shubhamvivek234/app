# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v6.0 shipped
Branch: main
Focus: Analytics & Reports Overhaul — Real Metrics, CSV Export, Pop-up Free PDF, Dark Theme UI

## Last Session Completed
Date: 2026-09-04
Completed:
- Legal & App Verification Overhaul:
  - Entity Registration: Integrated Government of India Udyam MSME details for **UNRAVLER TECHNOLOGIES** (UDYAM-JH-20-0144275, Proprietor: Bindu Prasad, Ranchi, Jharkhand).
  - Legal Pages (`Privacy.js`, `Terms.js`): Added Google API Limited Use compliance, Meta Graph permissions, India DPDP Act Grievance Officer details, and updated jurisdiction to Ranchi, Jharkhand, India.
  - New Pages (`RefundPolicy.js`, `Contact.js`): Added 7-day money-back policy (mandatory for Razorpay/Stripe) and full corporate contact page with phone and inquiry form. Wired routes in `App.js` and links in `Footer.js`.
  - Automated Data Deletion (`api/routes/webhooks.py`, `api/routes/user.py`, `DataDeletion.js`): Added Meta signed_request deletion & deauth webhooks, confirmation code generator, and public status API `GET /user/data-deletion-status/{code}` with live lookup in UI.
  - Test Suite (`tests/test_meta_data_deletion.py`): Added unit tests for signed_request parsing, webhook deletion, and status API; verified 7/7 passing.
  - Verified frontend production build (`main.37efaa03.js`).

## Active Work
Currently implementing: None
Next:
- Implement Postly-inspired features from roadmap (Phase 1: Workspace Approval Governance, AI Remix for Recurring Posts, First Comment Scheduling).

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
