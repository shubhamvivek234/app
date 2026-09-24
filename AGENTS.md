# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v9.1 Prosp AI Architectural Advantages & Live Streaming Shipped
Branch: main
Focus: Engage Section Hardening, Outreach Quality & Safety

## Last Session Completed
Date: 2026-09-24
Completed:
- Engage Section Deep Audit: 16 bugs (5 critical, 7 medium, 4 low), 20 improvements identified.
- **Critical Bugs Fixed (B1-B5)**: credentials:'include' on all 11 fetch calls; account validation (no silent mock fallback) via `_resolve_sender_account`; 2.5-8s Gaussian jitter between like→comment; `OutboundRateLimiter` wired into like/comment endpoints (429 on limit); `SafetyShield` circuit breaker auto-pauses accounts on 401/403/429.
- **Medium Bugs Fixed (B6/B9/B10-B12/B14-B16)**: Parallel fetch with `asyncio.gather` batches of 3; paginated posts feed (20/page + Load More); liked/discarded filter pills; like button loading spinner; toast respects auto-like; discard confirmation dialog; post media image rendering.
- **Improvements Shipped (I1/I3/I5)**: Bulk actions (select-all + batch like/discard); real contact enrichment via `VoyagerClient.fetch_profile_info`; engagement analytics summary bar (total/liked/commented/contacts).
- 73/73 outreach tests pass, frontend CI clean.
- Two commits: `61c9195` (critical bugs), `58674e8` (medium bugs + improvements).
- Deployed to EC2 + Vercel.

## Active Work
Currently implementing: None
Next:
- Remaining improvements I2/I4/I6-I20 from engage audit.
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
