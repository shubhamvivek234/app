# Unravler — Session Memory
> Read first, write last. Keep under 80 lines and concrete.

## Current Phase
Stage: v3.0 shipped
Branch: main
Focus: 6 Key Platform Expansions (Auto-UTM, Magic Review Links, Link-in-Bio, Branded PDF Reports, Draft Comments, AI Brand Voice)

## Last Session Completed
Date: 2026-08-29
Completed:
- Feature 1 (Auto-UTM & Link Shortener): built `api/routes/short_links.py`, `frontend/src/pages/ShortLinks.js`, collision-resistant slugs, click tracking analytics, and UTM presets.
- Feature 2 (Client Magic Review Links): built signed expiration tokens, unauthenticated review feed (`/review/:token`), 1-click approve/changes requested, and `ShareReviewModal.js` in `ApprovalQueue.js`.
- Feature 3 (Link-in-Bio Page Builder): built `api/routes/bio_pages.py`, customizable landing page (`frontend/src/pages/LinkInBio.js`, `PublicBioPage.js` at `/@:handle`), and live mobile phone preview.
- Feature 4 (Branded PDF Analytics Reports): executive performance report generator (`api/routes/analytics.py`), printable PDF export, and automated weekly/monthly email scheduling (`ExportReportModal.js`).
- Feature 5 (Post Draft Inline Comments): draft revision threads on post cards (`PostCommentsDrawer.js`), resolve/reopen status, and activity tracking.
- Feature 6 (Brand Voice & AI Persona Vault): persona guidelines (`api/routes/ai.py`), prohibited words filter, and settings tab (`BrandVoiceSettings.js`).
- Social Tools Hub Consolidation: integrated Link-in-Bio and Auto-UTM & Link Shortener as flagship growth tools in `frontend/src/pages/SocialTools.js` with category filters and streamlined the primary sidebar navigation.
- Verified test suite: 255/255 tests passed (100%), frontend bundle compiled (`npm run build`), deployed to EC2 cluster and Vercel.

## Active Work
Currently implementing: None
Next:
- Implement legal & app verification roadmap (`docs/APP_VERIFICATION_AND_LEGAL_PLAN.md`) when business details are provided.
- Finish Cloudflare R2 migration (direct-to-R2 presigned uploads) and eliminate any remaining local-disk media paths.

## Deploy Notes
- Frontend: Vercel auto-deploys from `main`.
- Backend: EC2 `ubuntu@51.20.210.184` at `/opt/socialentagler`:
  `docker compose --env-file backend/.env -f docker-compose.prod.yml up -d --build`

## Quick Checks
```bash
git status --short
CI=true npm run build --prefix frontend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/ -q
.venv/bin/python -m compileall api/routes/short_links.py api/routes/bio_pages.py api/routes/ai.py api/routes/analytics.py api/routes/posts.py api/main.py
```
