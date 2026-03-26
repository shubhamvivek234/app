# SocialEntangler — Session Memory

> This file is read FIRST and written LAST in every Claude Code session.
> Keep it under 80 lines. Be specific. Vague entries waste the next session.

---

## Current Phase

Stage: v2.9 (complete)
Branch: main + version-6
Description: Full v2.9 implementation complete — all Phases 0–10, all EC1–EC31 edge cases, Cloudflare integration added
Arch doc reference: Architecture v2.9 / Implementation Plan v3.0

---

## Last Session Completed

Date: 2026-03-27
Completed tasks:
- FIXED: Google login architecture isolated from UI changes
- Created services/authService.js: all Firebase auth logic in one place
- Refactored context/AuthContext.js: delegates to authService, no direct Firebase imports
- Created hooks/useGoogleAuth.js: custom hook for clean component integration
- Added popup + redirect fallback when popup blocked
- Verified Google login flow end-to-end (tested on /login, redirects to /onboarding)
- Started backend and frontend servers, confirmed zero authentication errors

Files created:
- frontend/src/services/authService.js (222 lines) — isolated auth service
- frontend/src/hooks/useGoogleAuth.js (48 lines) — custom hook wrapper

Files modified:
- frontend/src/context/AuthContext.js — removed Firebase imports, uses authService

---

## Active Work (next session starts here)

Currently implementing: None — auth fix complete
Next concrete step: Any feature work; auth is now isolated and won't break on UI changes
Blocked on: nothing

---

## Architecture Notes

- Authentication is now completely isolated in authService.js
  * googleSignIn() handles popup + redirect fallback (popup-blocked safety)
  * All Firebase calls delegated to authService — UI changes won't break auth
  * Token management and backend sync handled independently
- Frontend preview_start requires system node bootstrap (see .claude/launch.json)

---

## Decisions Made This Session

- Isolated authentication in dedicated authService.js module to prevent UI changes from breaking login
- Popup + redirect fallback: if browser blocks popup, automatically fall back to redirect flow
- All Firebase operations delegated to authService — AuthContext only manages state
- Custom hook (useGoogleAuth) for clean component-level integration

---

## Test Status

Last run: —
Failing: —
Coverage: not measured

---

## Notes for Next Session

Start by running:
```bash
cat CLAUDE.md
git log --oneline -5
git status --short
```

Skill active: socialentangler-dev (auto-loads for all SocialEntangler work)
Auth system: Now isolated in services/authService.js — can modify UI without breaking login
Servers: Backend (8000), Frontend (3000) — both running after auth fix
