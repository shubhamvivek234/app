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

Date: 2026-03-20
Completed tasks:
- Replaced all bg-white → bg-offwhite (#fefefb) across 48 frontend files
- Added offwhite custom color to tailwind.config.js
- Replaced #ffffff → #fffffb on login/signup panel backgrounds
- Integrated Cloudflare R2 (utils/storage.py), Turnstile (utils/turnstile.py), CDN cache purge
- Added TurnstileWidget.js + wired into LoginV1/SignupV1
- Fixed frontend server (craco launch config via system node bootstrap)
- Installed socialentangler-dev skill + starter files

Files changed:
- frontend/tailwind.config.js, frontend/src/**/*.js (48 files)
- backend/utils/storage.py, backend/utils/turnstile.py
- frontend/src/components/TurnstileWidget.js
- frontend/src/pages/LoginV1.js, SignupV1.js
- frontend/src/context/AuthContext.js
- .claude/launch.json (craco via /opt/homebrew/bin/node -e bootstrap)

---

## Active Work (next session starts here)

Currently implementing: Cloudflare integration is done — no active task
Next concrete step: Enable Cloudflare in production by setting STORAGE_BACKEND=r2 and TURNSTILE_ENABLED=true in production .env
Blocked on: nothing

---

## Known Issues

- Frontend preview_start requires system node bootstrap (see .claude/launch.json)
  because macOS sandbox blocks node_modules execution from worktrees
- TURNSTILE_ENABLED=false in dev (intentional — enable in production only)
- STORAGE_BACKEND=r2 set in backend .env — Firebase code preserved as fallback

---

## Decisions Made This Session

- Off-white color: #fefefb (bg-offwhite Tailwind) for all page backgrounds
- Login/signup panels: #fffffb
- Cloudflare R2 bucket: socialentangler-media (Asia Pacific, Standard)
- Feature-flagged storage: STORAGE_BACKEND env var (r2|firebase)

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
Backend worktree: .claude/worktrees/stupefied-matsumoto (feature/v2.9-implementation)
Frontend: /frontend/ on main + version-6 branches
