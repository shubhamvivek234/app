# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v9.1 Prosp AI Architectural Advantages & Live Streaming Shipped
Branch: main
Focus: URL Deep-Linking & History Sync, Relational Cascades, Live SSE Stream, Convergent DAG

## Last Session Completed
Date: 2026-09-24
Completed:
- Campaign Save & Close Visibility & Name Persistence: Fixed auto-draft name overwrites with `hasUserEditedName` ref and onBlur sync; updated `syncDraft()` to ensure creation on save; sorted `list_campaigns` by `updated_at` desc so newly saved drafts appear at top; updated `handleCloseWizard` in `OutreachApp` to navigate directly to campaigns tab and trigger fresh list re-fetch via `refreshKey`.
- Sequence Canvas Fluid Panning & Leftward Navigation: Added native drag-to-pan, two-finger trackpad panning, and wheel zoom to `SequenceCanvas`; added directional Move Left, Move Right, and Recenter controls to the toolbar to easily pan and inspect branch steps expanding to the left.
- 73/73 outreach tests pass, frontend CI clean (`CI=true npm run build`, 807.88 kB gzip main bundle).

## Active Work
Currently implementing: None
Next:
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
