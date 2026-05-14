# SocialEntangler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v2.9 shipped
Branch: main
Focus: R2 migration + composer reliability + onboarding reliability

## Last Session Completed
Date: 2026-05-14
Completed:
- Frontend: fixed Create Post crash on account selection (React max-update-depth #185).
  Files: `frontend/src/pages/CreatePostForm.js`
- Frontend: normalized social-account payloads + cache key bump (`social_accounts_cache_v2`).
  File: `frontend/src/lib/api.js`
- Frontend: same-platform account switcher shows circular avatars.
  File: `frontend/src/components/composer/PlatformEditor.js`
- Backend (modular app): added missing `PATCH /api/auth/me` so onboarding “Next” + payment completion can update profile fields.
  File: `api/routes/auth.py`
- Backend/Frontend: fixed Twitter/X OAuth flow by adding required PKCE params (code_challenge/S256) and sending `state` on callback.
  Files: `api/routes/accounts.py`, `frontend/src/pages/OAuthCallback.js`
- Frontend: changed OAuth connect UX to use same-tab redirects (no popup/new-tab).
  Files: `frontend/src/pages/OnboardingConnect.js`, `frontend/src/pages/ConnectedAccounts.js`

## Active Work
Currently implementing: None
Next: Finish Cloudflare R2 migration (direct-to-R2 presigned uploads) and eliminate any remaining local-disk media paths.

## Deploy Notes
- Frontend: Vercel auto-deploys from `main`.
- Backend: EC2 `ubuntu@51.20.210.184` at `/opt/socialentagler`:
  `docker compose --env-file backend/.env -f docker-compose.prod.yml up -d --build`

## Quick Checks
```bash
git status --short
CI=true npm run build --prefix frontend
python3 -m compileall api/routes/auth.py
```
