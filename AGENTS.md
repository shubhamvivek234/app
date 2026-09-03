# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v6.0 shipped
Branch: main
Focus: Analytics & Reports Overhaul — Real Metrics, CSV Export, Pop-up Free PDF, Dark Theme UI

## Last Session Completed
Date: 2026-09-04
Completed:
- Legal & App Verification Overhaul & Contact Email Standardized:
  - Standardized corporate contact email to `contact@unravler.com` across all legal pages, contact forms, and email utilities.
  - Removed phone / WhatsApp details (+91 9031777441) from Contact, Terms, Privacy, Data Deletion, and Refund pages to rely on official email and web contact.
- Permanent Account Deletion Pipeline (GDPR / DPDP Compliant):
  - Frontend (`Settings.js`): Added strict `DELETE` text typing confirmation dialog in Danger Zone, with disabled action state, loading indicators, and post-deletion logout.
  - Auth Layer (`api/deps.py`): Immediately rejects (`403 Forbidden`) active tokens/sessions for accounts with `deletion_pending` or `deleted` status.
  - Cascading Erasure Worker (`celery_workers/tasks/gdpr.py`): Purges all 18 collections (posts, social_accounts, media_assets, bio_pages, short_links, notifications, workspaces), deletes physical files from Cloudflare R2 / S3 storage, deletes Firebase Auth identity, cancels gateway subscriptions, and hard-deletes `db.users`.
  - Test Suite (`tests/test_account_erasure.py`): Added 3 unit tests verifying queued status, 403 authorization lock, and cascading storage & collection purge (297/297 passing).
  - Verified frontend build (`main.1ecc0c08.js`).

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
