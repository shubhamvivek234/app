# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v8.6 LinkedIn Winning Templates Parity & E2E Regression Engine Shipped
Branch: main
Focus: Winning Sequence Templates, Fixed Right Sidebar Inspector, Auto-Drafting, Unified Sync & Intent Engine

## Last Session Completed
Date: 2026-09-23
Completed:
- Winning Templates Engine Parity (`media_1790104784825.png`, `media_1790104824235.png`, `media_1790104866987.png`):
  - Prebuilt 4 winning templates (`Connect and follow up`, `Profile warm-up`, `Voice note outreach`, `Multi-touch InMail & engage`).
  - Dynamic template gallery table with Uses/Acceptance/Reply KPI columns, `[ Use ]` 1-click campaign generator, and custom template deletion.
  - Custom sequence templates support (`POST /sequences/templates`, `GET /sequences/templates`, `DELETE /sequences/templates/{id}`).
  - Fixed-length right sidebar in `SequenceCanvas.js` matching forensic layout (empty state with pencil icon; inspector with delay stepper & script editor; does not grow with canvas).
  - Sequence loading from `/api/v1/outreach/sequences/{id}` and debounced auto-save with `flattenTreeToDAG`.
  - Comprehensive end-to-end regression test suite (`tests/test_outreach_e2e_regression.py`).
- 58/58 outreach tests pass, frontend CI clean (807.89 kB gzip main bundle).

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
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/ -q
.venv/bin/python -m compileall api/routes/ai.py utils/free_llm_router.py utils/content_repurposer.py
```
