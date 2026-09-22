# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v8.0 LinkedIn Outbound & AI Sequence Engine Shipped (Option A Prosp Parity)
Branch: main
Focus: Decoupled Cold Outbound Automation, 1:1 JIT Residential Proxies, Voice Cloning, Unified Inbox

## Last Session Completed
Date: 2026-09-23
Completed:
- Locked right-side drawer to fixed viewport height (`h-full max-h-full overflow-hidden`) so it never stretches vertically when sequence canvas expands (`0681559`).
- Deep architectural & visual audit of `media_1790103490135.png` implemented on Wizard Step 3:
  - Heading and subheadings unboxed to background level matching Prosp layout.
  - Interactive 30-min time slot dropdowns with clock badges, inline `✕` deletion, `+` range adder, and `📋` copy-to-all weekdays.
  - Fine horizontal dividers between every weekday row (S-M-T-W-T-F-S).
  - Timezone selector with UTC offset and local time previews.
  - Safe defaults reset trigger and 8 daily limits stepper controls (`[-] [ 20 ] [+]`).
  - Pre-flight review modal and Connect LinkedIn modal integration before launching (`1bc9fa6`).
- Replaced top-left sidebar sparkle icon in `OutreachLayout.js` with official circular (`rounded-full`) Unravler logo mark (`UnravlerLogo` component with white color and hover scale/active feedback).
- Full forensic parity & end-to-end audit for Voice Cloner (`media_1790020955632.png`):
  - Added connected sender account selector on voice profiles with instant persistence.
  - Implemented real volume/silence detection with Prosp error prompt on silent recordings.
  - Fixed synthetic audio generator producing audible WAV bytes for browser preview.
  - Integrated `SequenceNodeType.VOICE_NOTE` into `SequenceExecutor` with Voyager dispatch.
- 40/40 unit tests pass, frontend CI build clean, pushed to `main`, EC2 synced.

## Active Work
Currently implementing: None
Next:
- Verify live preview and campaign run with user.

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
