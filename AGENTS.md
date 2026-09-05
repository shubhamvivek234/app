# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Authentication Lifecycle & Bug Fixes (Logout, Login, Signup, Password Reset)

## Last Session Completed
Date: 2026-09-06
Completed:
- Single-Action Logout & Zero Resurrection: Fixed dropdown unmount bug in `DashboardLayout.js` (`setOpen(false)` unmounted logout button prematurely); added `isLoggingOutRef` latch in `AuthContext.js` to suppress Firebase auth listener events during logout; relaxed `/auth/session/logout` dependency so it clears cookie and returns 204 without throwing 401.
- Immediate Login & Signup Navigation: Added `resolvePostAuthDestination` redirects with `finally { setLoading(false) }` across `LoginV1..V4.js` and `SignupV1..V4.js`, eliminating double-action delays and race conditions.
- Resilient Forgot Password: Added 2.5s timeout on IAM link generation with immediate Google Identity Toolkit REST fallback (`sendOobCode`); added client fallback in `authService.js` to guarantee fast delivery without hangs.
- Deploy & Verification: All 356 unit tests passing; frontend built cleanly; deployed to EC2 production (`socialentagler-api-1` and `socialentagler-worker-1` healthy); verified `/api/auth/session/logout` (204) and `/api/auth/password-reset/request` (200).

## Active Work
Currently implementing: None
Next:
- Monitor user onboarding and auth telemetry in PostHog.

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
