# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v5.7 shipped
Branch: main
Focus: Single-Click Instant Logout & State Synchronization

## Last Session Completed
Date: 2026-09-02
Completed:
- Single-Click Logout Race Condition Fix (commit `3b960a3`):
  - Identified root cause of double-click logout requirement: asynchronous network request (`logoutBackendSession`) delayed state cleanup while `handleLogout` synchronously routed to `/login`, causing `PublicRoute` to see stale `user` and immediately bounce back to `/dashboard`.
  - In `AuthContext.js`, synchronously reset all client auth state (`clearAuthData()`, `token`, `user`, `firebaseUser`, `authIssue`, `sessionStorage`) immediately before running backend revocation and Firebase sign-out concurrently (`Promise.allSettled`).
  - Updated `handleLogout` across `DashboardLayout.js`, `OnboardingHeader.js`, and `SubscriptionExpired.js` to async/await `logout()` with a loading state guard (`isLoggingOut`) and `{ replace: true }` navigation.
  - Verified clean frontend build (`main.bc67e0e7.js`), deployed live to Vercel (`main.6e6820c0.js`), and synced EC2.

## Active Work
Currently implementing: None
Next:
- Implement legal & app verification roadmap (`docs/APP_VERIFICATION_AND_LEGAL_PLAN.md`) when business details are provided.

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
