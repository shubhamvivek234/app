# SocialEntangler — Session Memory

> Read first, write last. Keep specific and short.

## Current Phase

Stage: v2.9 complete
Branch: main + version-6
Focus: Cloudflare R2 migration for uploads/publish pipeline
Arch refs: Architecture v2.9 / Implementation Plan v3.0

## Last Session Completed

Date: 2026-05-13
Completed tasks:
- Added direct-to-R2 backend API expected by frontend: `/api/upload/session`, `/api/upload/complete`, `/api/upload/{media_job_id}`, `/api/upload/{media_job_id}/abort`
- Standardized storage config in `backend/utils/storage.py` with `CF_R2_*` as primary and `CLOUDFLARE_R2_*` + `CLOUDFLARE_CDN_DOMAIN` as compatibility aliases
- Added presigned single-part + multipart R2 upload support and managed URL/key parsing helpers
- Removed backend upload fallback to local disk in `backend/server.py` for `/api/upload` and `/api/public/upload/from-url`
- Insert legacy upload results into `media_assets` so old and new upload paths share metadata
- Updated Celery media cleanup to delete only managed storage URLs via shared storage helper
- Switched `frontend/src/pages/BulkVideoUpload.js` from dead `/api/v1/upload/media` flow to shared `uploadMedia()` + `waitForUploadReady()`
- Added unit tests for storage aliasing and managed URL parsing

Files created:
- `backend/tests/test_storage_utils.py` — storage alias + URL parsing tests

Files modified:
- `backend/utils/storage.py`
- `backend/server.py`
- `backend/celery_tasks.py`
- `frontend/src/pages/BulkVideoUpload.js`

## Active Work

Currently implementing: R2 migration backend/core flow done in code
Next concrete step: Run end-to-end upload test against real R2 creds/CORS and verify scheduled publish workers can fetch `https://media.unravler.com/...`
Blocked on: real environment verification, secret rotation if old R2/API credentials shown in screenshots were not rotated

## Architecture Notes

- Frontend already preferred direct upload; backend was missing those routes. They now exist.
- New direct upload flow stores `media_assets` rows in `uploading` then `ready` state.
- Public media URLs now come from shared storage helper and should resolve to `CF_R2_PUBLIC_URL` / `media.unravler.com`
- `backend/utils/storage.py` is now the single storage contract for env resolution, presigned uploads, deletes, and URL parsing
- Local `/uploads` mount still exists only for backward compatibility; new backend upload paths no longer write there

## Decisions Made This Session

- Keep `CF_R2_*` as canonical env names; support old `CLOUDFLARE_R2_*` names as fallback during migration
- Prefer direct browser-to-R2 uploads with multipart for larger files instead of proxying bytes through FastAPI
- Keep legacy `/api/upload` route operational but store the file in managed cloud storage only
- Cleanup logic should delete only URLs recognized as managed storage, not arbitrary external media URLs

## Test Status

Last run:
- `python3 -m compileall backend/server.py backend/celery_tasks.py backend/utils/storage.py backend/tests/test_storage_utils.py`
- `backend/venv/bin/pytest backend/tests/test_storage_utils.py -q`
Result: compile passed, 3 tests passed

## Notes for Next Session

Start with:
```bash
cat AGENTS.md
git status --short
git log --oneline -5
backend/venv/bin/pytest backend/tests/test_storage_utils.py -q
```

Important:
- Do not touch unrelated `.claude/worktrees/*` changes
- Auth isolation files from 2026-03-27 remain intact; avoid unnecessary edits there
- Secrets previously shown in chat should be treated as compromised until rotated
