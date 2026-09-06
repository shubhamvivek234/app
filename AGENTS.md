# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v7.0 shipped
Branch: main
Focus: Authentication Lifecycle & Bug Fixes (Logout, Login, Signup, Password Reset)

## Last Session Completed
Date: 2026-09-06
Completed:
- Standardized Auth Errors: Mapped `auth/invalid-credential`, `auth/wrong-password`, and `auth/user-not-found` to "Incorrect email or password. Please double-check and try again." via `getAuthErrorMessage()`; sanitized bot protection 403s and stripped raw SDK prefixes; removed duplicate toast calls from `AuthContext.js`.
- Password Manager & Credential Saving: Added semantic `form method="POST" autoComplete="on"`, explicit `name` and standard `autoComplete` attributes (`username email`, `current-password`, `new-password`) across all Login (V1–V4), Signup (V1–V4), AcceptInvite, and ForgotPassword pages; integrated W3C Credential Management API (`window.PasswordCredential` + `navigator.credentials.store()`) into `emailSignIn` and `emailSignUp` to reliably trigger browser/keychain "Save Password" prompts.
- Build & Verification: Frontend built cleanly (`1.25 MB` gzipped bundle); all 350 unit tests passing (0 failures); Python compiled cleanly.

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
