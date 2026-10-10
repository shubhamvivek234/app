# Unravler.io v2.54 deployment — 2026-10-10

The user authorized committing and deploying the reverified local changes. Application commit: `ccf58195dfa01945f91d916243bf2e4e5c7c5858`. Previous production checkout: `81f1677754807dc7ed88ade4d655f7a5b3ea51da`.

## Scope and transport

The commit contains the three offline restore helpers, 95 focused tests, corrected architecture/release documents and reverification memory. The helpers still cannot establish authenticated source completeness, restore real reply suppression or activate execution. The implementation boundaries and 841-check restore regression are in [the reverification report](UNRAVLER_IO_RESTORE_HELPERS_REVERIFICATION.md).

All 95 focused checks passed again immediately before commit in 1.49 seconds, with one existing multipart deprecation warning. Unrelated worktrees, coverage data and wedding artifacts were excluded from the commit.

At backend deployment time, GitHub pushes failed on both the local computer and production server because usable authentication was unavailable. GitHub `main` was still at `04ca28b5d1dd7bd213ea67e951970e19fd93bdf3`; the earlier v2.23–v2.50 commit and this release had not been pushed then. The deployment used a verified Git bundle over the existing SSH connection to the established EC2 checkout `/opt/socialentagler`, with a fast-forward-only update to the exact application commit. The v2.54 helper commit itself contains no frontend changes; frontend deployment was not part of that SSH operation.

## GitHub synchronization after sign-in

After the user signed in, GitHub CLI verified the active `shubhamvivek234` account using macOS keyring storage. All three pending commits (`81f1677`, `ccf5819`, `12f0315`) were pushed successfully to `origin/main`, and a separate remote-ref read confirmed `12f0315cf11df54bb225040902c907f61be7a8db`. Authentication is no longer blocking local pushes.

The older `81f1677` release includes four frontend integration-screen/delivery-formatting source/test files; those earlier changes are included in this synchronization. GitHub reported automatic Vercel deployments for both `app` and `app-fgv2` as pending at the synchronization check. That observed status does not confirm a completed frontend deployment. The follow-up synchronization record changes documentation only.

GitHub CLI initially selected an incompatible `/usr/local/bin/git`. Configuring the credential helper with `/usr/bin` first in the command's PATH resolved that tool invocation, without replacing the older executable or changing the user's shell configuration. Official GitHub CLI 2.102.0 is installed at `/opt/homebrew/bin/gh`; its Mac download checksum was verified after Homebrew could not supply a bottle for the preview OS.

### Automated-check observations after the push

GitHub successfully received the release and the documentation follow-up `cfe7bc3`. This synchronization is not a green-CI certification. For application-equivalent commit `12f0315`, the frontend workflow stopped during dependency installation: `npm ci` reported that package.json and package-lock.json disagree, with motion/framer-motion/motion-dom 13.5.1 and motion-utils 13.5.0 missing from the lock. The production build step did not run. [Frontend job](https://github.com/shubhamvivek234/app/actions/runs/38044167085/job/114190220097).

Security workflow checks also reported failures. SAST annotations include a Git process exit 128; TruffleHog reports identical BASE and HEAD and therefore no scan. NPM/Python dependency audits and Trivy also failed; their causes have not been established by this synchronization check. Backend tests were still running at observation. Failed scans do not establish a clean security result. [Security workflow](https://github.com/shubhamvivek234/app/actions/runs/38044167066).

The `12f0315` Vercel `app` deployment subsequently reported success; `app-fgv2` remained pending at the latest observation. The documentation follow-up triggered its own automatic deployment statuses. No completed `app-fgv2` deployment or green combined release is claimed. Application or workflow repairs were not made during this authentication/push step.

## Build and startup

The existing production Compose configuration rebuilt API, worker, media worker, video worker, beat and MCP successfully. Previous images were retained under service-specific `rollback-81f1677-v254` tags.

The initial simultaneous restart exceeded its 180-second dependency wait. During startup the approximately 911MiB host was using about 985MiB of swap and had a load average of 5.87. The API processes had no restarts, tracebacks or reported exceptions at inspection. Workers and beat were gracefully stopped; API and MCP then passed their health checks. Workers were brought back one at a time, each reporting ready before the next, followed by beat. No persistent concurrency, flag, credential or configuration change was made to resolve the startup load.

## Verified runtime

- API and MCP report healthy. API, all three workers and beat are running with zero container restarts at inspection.
- The four reviewed restore source files, including unchanged `restore_epoch.py`, match the application commit byte-for-byte in all five Python containers; compilation checks pass there. MCP does not contain those Python files and was checked through its own health status.
- A synthetic offline smoke check inside the production API image passes artifact signature verification, independent local-view divergence, non-authorizing plan/authority checks and reply timestamp validation/future rejection. It reads/writes no domain records and makes no provider request or grant.
- Internal `/health` returns HTTP 200 with `status: ok`. Internal `/ready` returns HTTP 200 with the same pre-deployment result: MongoDB, queue/cache Redis, Firebase admin and R2 storage are OK; `auth_password_reset` remains `degraded:custom_link_domain`.
- The public outreach campaigns endpoint returns HTTP 401 without authentication. Public `/ready` returns the existing Nginx HTTP 403 restriction.
- Production `backend/.env` and Compose file fingerprints match their pre-deployment values. Selected runtime flags match the baseline in every checked service. Outreach live actions, health monitoring, voice Studio/preparation, conditional launch, mailbox connection/send/sync, finder and restore fencing remain false. The pre-existing integration flag remains true; this release does not verify or enable any integration activation.

All three expected worker nodes answered Celery ping with `pong`; node identities were matched to the worker, media-worker and video-worker containers. A subsequent internal health check remained OK. The deployment record and session-memory follow-up change documentation only; runtime images continue to contain the verified application commit above.

The release does not certify actual provider operation, IAM/kernel egress, a live pilot, authenticated restore recovery or safe reactivation.
