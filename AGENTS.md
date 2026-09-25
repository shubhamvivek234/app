# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v9.1 Prosp AI Architectural Advantages & Live Streaming Shipped
Branch: main
Focus: Engage & Grow verification, outreach safety, and campaign warm-up

## Last Session Completed
Date: 2026-09-25
Completed:
- LinkedIn Cold Outreach Campaign audit: create/edit/template, leads, sequence, schedule, limits, launch/pause/resume, duplicate/delete/restore, and analytics.
- Fixed phantom campaign/template success, sequence save/lifecycle issues, workspace ownership checks, stale campaign metrics, invalid schedule/cap handling, and failed actions being counted as success.
- Added a scheduled campaign runner with due-step claiming, explicit wait/branch handling, verified LinkedIn profile URNs, and fail-safe mock defaults.
- Removed fabricated prospect enrollment; disabled disconnected lead sources and unsupported sequence actions/limits. Prompt tokens now preview as placeholders and cannot be launched as literal copy.
- Improved CSV URL normalization, template variables, timezone/schedule display, and sender/launch validation.
- Earlier Engage fixes B1-B6/B9-B10/B12-B16 and I1/I3/I5 were committed (`61c9195`, `58674e8`) and deployed, but B7/B8/B11 remained incomplete in practice.
- This session fixed B7 (verified-only enrichment; legacy guessed identities hidden/reverified), B8 (Celery fetch with 3 concurrent requests, status/polling), and B11 (client lock + atomic backend claim). Like/comment now queue on the outreach worker; failed Voyager calls no longer count as successful engagement.
- Added sender picker, true list stats, contact deletion/history, CSV report, writing styles in AI comments, post-age warnings, keyboard shortcuts, and media URL extraction/cards. Bulk likes now have human spacing.
- Linked Engage lists to draft campaigns; campaign launch checks every lead has confirmed engagement and delays first action 24/48h. No unreviewed scheduled auto-comments (I14); the unsupported 12%→50% conversion claim was removed.
- Local verification: 10 Engage tests passed, Python compile clean, frontend CI build succeeded with third-party source-map warnings. Broader campaign detail/short-link tests have pre-existing fixture/DNS failures. Live UI check blocked by locked Mac.
- Release commit `d8ad55d` was pushed to `origin/main` on 2026-09-25. Frontend should auto-deploy via Vercel. Backend EC2 deploy is blocked on this Mac by missing SSH identity (`Permission denied (publickey)`).

## Active Work
Currently implementing: None
Next:
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
