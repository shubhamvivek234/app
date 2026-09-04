# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v6.8 shipped
Branch: main
Focus: Adaptive Multi-Network Master Composer & Platform-Aware Common Post

## Last Session Completed
Date: 2026-09-05
Completed:
- Adaptive Visibility (`CreatePostForm.js`): Automatically hides Common Post when 1 account is selected to avoid duplicate boxes; renders Common Post as Master Composer when 2+ accounts are selected.
- Real-Time Multi-Network Limit Badges (`PlatformEditor.js`, `mediaValidation.js`): Live per-platform character pills (`[X: 180/280]`, `[IG: 180/2200]`, etc.) with amber/red limit alerts and dynamic strictest remaining countdown.
- 1-Click Optimization in Master Composer: Surfaced 9:16 auto-fit, auto-compress, and silent audio track fixes directly in Common Post, updating assets once for all destinations.
- Universal First Comment & Alt Text Preservation: First comments in Common Post auto-propagate to Instagram & LinkedIn; image alt texts are preserved on submission.
- Non-Destructive Override Sync: Safe reordering/removing preserves platform-specific crops and custom media.
- Test Suite: 327/327 backend tests passing; 21/21 Jest tests passing; frontend production build clean.

## Active Work
Currently implementing: None
Next:
- Real-world validation with multi-network scheduled publishing.

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
