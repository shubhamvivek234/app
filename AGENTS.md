# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: Paid outreach pilot deployed behind disabled live-action flag
Branch: main
Focus: Verify purchased IPRoyal sender seats, billing ops, and live smoke before enabling actions

## Last Session Completed
Date: 2026-09-28
Completed:
- Added manual Engage Draft & Review: save from post/AI suggestion, edit, copy, open on LinkedIn, self-report completion, dismiss. Drafts never send to LinkedIn or count as verified engagement; list/contact deletion cascades to drafts.
- Added recorded-only Engage report and print stylesheet/button labeled “Print / Save as PDF”; no invented response-rate attribution.
- Added explicit optional campaign auto-launch arm with `warming_up` status, 100% timestamped-engagement gate for the selected Engage list, 24/48h cooldown, lead/sequence snapshot, and worker revalidation of sender session, proxy, schedule, and launch rules. `OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED=false` by default pending product/legal decision.
- Added visible cancel controls and fail-closed guards: no armed-list unlink/delete, no edits/imports during warm-up, no reauthorization on campaign delete/restore, working-hours trigger check, and sanitized worker/session errors.
- Subscription cancellation now pauses campaigns/senders, cancels queued tasks, and reports failed proxy releases without discarding their records. Settings Help copy no longer implies jitter/proxies make unauthorized automation safe.
- Verification: 148 outreach backend tests and 44 outreach frontend tests pass; Python compile, diff check, and frontend production build pass with existing dependency/Tailwind/source-map warnings. No live LinkedIn/proxy end-to-end check.
- Release commits through `ec74472` were pushed to `origin/main` on 2026-09-26. Frontend should auto-deploy via Vercel. Backend EC2 is deployed; API and MCP are healthy, and beat/worker/worker_media/worker_video are running.
- Deployment fixes: added `outreach/` to media worker and beat Docker images so the shared Celery app can import outreach tasks.
- Production `WEBSHARE_API_KEY` is configured in EC2 `backend/.env` (secret not committed). Containers were recreated and API reports a live, non-mock key.
- Fixed Prosp browser CORS and replaced nonexistent Webshare per-proxy order/delete calls with documented plan/proxy inventory reads and atomic local proxy reservations. Removed false zero-idle-cost copy. Commit `b638bf8` pushed and deployed on 2026-09-26.
- Verification: 152 outreach backend tests, 19 focused frontend tests, production build, and public `app.prosp.ai` CORS preflight passed. EC2 API/MCP healthy; beat and workers running. Webshare API reports only an active free/default plan, so live sender connection remains blocked until a dedicated static residential (ISP) proxy is added.
- IPRoyal pilot support is committed and deployed (`15f85d6`): server-side provider switch (`OUTREACH_PROXY_PROVIDER`), one manually purchased ISP IP with country/URL validation, encrypted credentials, atomic one-sender lease, same-sender reconnect, and migration back to Webshare. Webshare remains default; no auto-purchase, renewal, or cancellation.
- Connection UI now accepts the purchased proxy country and supports sender reconnection; billing copy distinguishes app assignment from provider charges. Setup: `docs/OUTREACH_PROXY_PROVIDERS.md`. Verification: 168 outreach backend tests, 46 frontend tests, Python compile, Bandit, diff check, Compose config, and production build pass. No live IPRoyal or LinkedIn test yet because no purchased IPRoyal proxy is configured.
- Paid pilot lifecycle is committed and deployed (`24f52c5`): $59/month/sender invite-only request flow, no trial/checkout; verified external invoice and 1–5 country-matched IPs required before operator grant. One requested country per workspace in this pilot.
- Added managed IPRoyal static-IP inventory, workspace-bound one-IP-per-sender leases, async encrypted connection verification, soft disconnect and same-sender reconnection; no automatic provider purchase, renewal, or payment collection.
- Paid-term checks now guard campaign launch, sequence, Engage, and inbox workers. Expiry pauses work, scrubs sender/pending-job secrets, releases only pending reservations, and retains connected sender IP leases through provider expiry. `OUTREACH_LIVE_ACTIONS_ENABLED=false` remains default.
- Safety fixes: real IPRoyal health checks cannot be bypassed by mock Webshare config; paid connection rejects mock LinkedIn auth; unpaid draft editing remains available. Operator runbook in `docs/OUTREACH_PROXY_PROVIDERS.md`.
- Verification before commit: 179 outreach backend tests, 47 outreach frontend tests, production frontend build, Python compile, Bandit, and diff check pass. Build has existing dependency/Tailwind/source-map warnings. Broad backend suite still fails in unrelated `tests/test_account_erasure.py` missing `query_string` test scope.
- Deployment: pushed `24f52c5` to `origin/main`; EC2 backend pulled and rebuilt API, beat, MCP, worker, worker_media, worker_video. Docker reports API/MCP healthy. Internal `/health` OK and `/ready` degraded only for existing `auth_password_reset` custom-link-domain check. Public `/health` is intentionally Nginx-blocked.

## Active Work
Next:
- Obtain product/legal approval and a purchased IPRoyal static ISP IP; verify external billing workflow, configure managed inventory, and run live sender/proxy/worker smoke tests before production enablement. Do not claim production readiness from mocks.
- Add merchant processor/webhook reconciliation and automated provider procurement only after provider/payment contracts and real API validation. Current pilot fulfillment remains manual and operator-gated.
- Extend the pilot request schema to per-sender country before mixed-country workspaces; do not silently substitute country or reuse another customer's held IP.
- Webshare migration needs a managed inventory importer and lease transfer; the old `OUTREACH_PROXY_PROVIDER` switch alone does not migrate this paid pilot.
- Product/legal go-or-no-go before public rollout of session-based outreach; validate the Webshare provisioning endpoint and region availability with a real LinkedIn connection attempt before claiming live readiness.
- Scheduled Engage scraping/AI drafting and unattended like/comment dispatch remain unimplemented; any automatic LinkedIn interaction requires separate product/legal approval.
- Decide whether to migrate historical plaintext JSESSIONID records; newly connected/refreshed senders use encrypted storage.
- Live logged-in Engage smoke test after Mac unlock; review whether scheduled auto-engagement should instead be a human-approved queue.
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
