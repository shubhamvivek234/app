# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v9.1 Prosp AI Architectural Advantages & Live Streaming Shipped
Branch: main
Focus: Engage Draft & Review and guarded campaign warm-up completion

## Last Session Completed
Date: 2026-09-26
Completed:
- Added manual Engage Draft & Review: save from post/AI suggestion, edit, copy, open on LinkedIn, self-report completion, dismiss. Drafts never send to LinkedIn or count as verified engagement; list/contact deletion cascades to drafts.
- Added recorded-only Engage report and print stylesheet/button labeled “Print / Save as PDF”; no invented response-rate attribution.
- Added explicit optional campaign auto-launch arm with `warming_up` status, 100% timestamped-engagement gate for the selected Engage list, 24/48h cooldown, lead/sequence snapshot, and worker revalidation of sender session, proxy, schedule, and launch rules. `OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED=false` by default pending product/legal decision.
- Added visible cancel controls and fail-closed guards: no armed-list unlink/delete, no edits/imports during warm-up, no reauthorization on campaign delete/restore, working-hours trigger check, and sanitized worker/session errors.
- Subscription cancellation now pauses campaigns/senders, cancels queued tasks, and reports failed proxy releases without discarding their records. Settings Help copy no longer implies jitter/proxies make unauthorized automation safe.
- Verification: 148 outreach backend tests and 44 outreach frontend tests pass; Python compile, diff check, and frontend production build pass with existing dependency/Tailwind/source-map warnings. No live LinkedIn/proxy end-to-end check.

## Active Work
Currently implementing: None. This Engage/campaign work and earlier Leads, Analytics/Swipe/Inbox, Home/Campaign/Accounts, session connection, and Settings patches remain local and uncommitted.
Next:
- Review/commit/deploy local outreach patches when requested; smoke test first-run, a connected sender, Draft & Review, and real Voyager inbox payload after deployment.
- Product/legal go-or-no-go before public rollout of session-based outreach; validate the Webshare provisioning endpoint and region availability with the provider before claiming live readiness.
- Scheduled Engage scraping/AI drafting and unattended like/comment dispatch remain unimplemented; any automatic LinkedIn interaction requires separate product/legal approval.
- Decide whether to migrate historical plaintext JSESSIONID records; newly connected/refreshed senders use encrypted storage.
- Load/provide the EC2 deploy SSH key, then run backend deploy from `/opt/socialentagler`.
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
