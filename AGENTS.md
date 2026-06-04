# SocialEntangler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v2.9 shipped
Branch: main
Focus: auth hardening + R2 migration + composer reliability

## Last Session Completed
Date: 2026-06-04
Completed:
- Backend: added Firebase session-cookie auth with `POST /api/auth/session` and `POST /api/auth/session/logout`; browser auth is now cookie-first with bearer fallback.
  Files: `api/routes/auth.py`, `api/deps.py`, `utils/session.py`, `api/models/user.py`
- Backend: `/api/auth/password-reset/request` now uses Firebase-managed reset emails, Turnstile, rate limiting, and generic success responses that do not leak account existence.
  Files: `api/routes/auth.py`, `docker-compose.yml`
- Backend: added `email_verified` propagation from Firebase claims into Mongo bootstrap/update flow and exposed it from `/api/auth/me`.
  Files: `api/deps.py`, `api/models/user.py`, `api/routes/auth.py`
- Backend: gated verified-email-required actions for social account connect, publish/schedule/retry/approve, team invite/accept, recurring rules, and bulk CSV scheduling.
  Files: `api/routes/accounts.py`, `api/routes/posts.py`, `api/routes/team.py`, `api/routes/recurring.py`, `api/routes/bulk_upload.py`
- Frontend: removed auth-page roulette; login/signup now use the hardened V1 flows consistently with Turnstile.
  Files: `frontend/src/pages/Login.js`, `frontend/src/pages/Signup.js`, `frontend/src/pages/LoginV1.js`, `frontend/src/pages/SignupV1.js`
- Frontend: moved the web app away from `localStorage` bearer auth toward HttpOnly cookie sessions while keeping compatibility fallback for legacy callers.
  Files: `frontend/src/services/authService.js`, `frontend/src/context/AuthContext.js`, `frontend/src/lib/http.js`, `frontend/src/lib/api.js`, `frontend/src/lib/requestOAuthUrl.js`, `frontend/src/lib/requestOAuthCallback.js`, `frontend/src/hooks/usePostStatusStream.js`
- Frontend: added real `/forgot-password` and replaced the dead verify-email flow with Firebase action-code verification plus backend resync.
  Files: `frontend/src/pages/ForgotPassword.js`, `frontend/src/pages/VerifyEmail.js`, `frontend/src/App.js`, `frontend/src/pages/AuthCallback.js`
- Tests: added auth-security regressions for session exchange, password reset privacy, cookie-first auth, and verified-email enforcement.
  Files: `tests/test_auth_security.py`

## Active Work
Currently implementing: None
Next:
- Commit/deploy the auth hardening once requested and verify the live cookie-session flow on Vercel + EC2.
- Finish Cloudflare R2 migration (direct-to-R2 presigned uploads) and eliminate any remaining local-disk media paths.

## Deploy Notes
- Frontend: Vercel auto-deploys from `main`.
- Backend: EC2 `ubuntu@51.20.210.184` at `/opt/socialentagler`:
  `docker compose --env-file backend/.env -f docker-compose.prod.yml up -d --build`

## Quick Checks
```bash
git status --short
CI=true npm run build --prefix frontend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/test_auth_security.py tests/test_publish_feed.py tests/test_accounts_route.py -q
python3 -m compileall api/routes/auth.py api/deps.py api/routes/posts.py api/routes/accounts.py api/routes/team.py api/routes/recurring.py api/routes/bulk_upload.py utils/session.py
```
