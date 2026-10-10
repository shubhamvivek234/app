# Unravler.io v2.54 deployment — 2026-10-10

## Final authorized rollout after GitHub sign-in

The latest verified application release is `e506747cc25f2dd400250c7a8af0b60037a449a3`, pushed to GitHub and deployed to EC2 and both Vercel production projects. The earlier observations below describe the original deployment and synchronization, rather than the final rollout status. A subsequent documentation-only record does not change the application source or installed dependencies.

Release repairs are bounded to `frontend/package-lock.json`, `requirements.txt` and `.github/workflows/security.yml`. Commit `346f672` restores the missing motion dependency tree, removes TruffleHog's equal base/head override and debug output, and replaces unsupported pip-audit arguments with its valid vulnerability-blocking command. Commit `e506747` finishes the JWT update at PyJWT 2.15.1 after the broader audit identified additional fixes beyond 2.14.0. Existing Yarn resolutions were preserved; npm's incidental Yarn rewrite was discarded before commit. The repairs do not disable or suppress security findings.

### Validation and frontend

- A clean temporary npm installation and a production build with `CI=true` and source maps disabled passed. All 99 outreach frontend tests passed across 22 suites. The original workspace dependencies were preserved.
- With the final PyJWT 2.15.1, all 39 authentication/account/OAuth/token tests passed in 40.10 seconds, and all 95 restore-helper checks passed in 1.12 seconds. Valid OAuth state was accepted and malformed/expired state rejected in an additional offline smoke check. Existing multipart and short test-key warnings remain. The earlier 841-check restore regression is historical evidence; it was not rerun during this deployment repair.
- Independent code/Python review approved both the three-file repair and the final JWT refinement. Independent YAML/lock/OAuth checks and seven JWT smoke checks passed. No remaining HIGH/CRITICAL finding was reported in the reviewed diff; this is not approval of the wider dependency stack.
- [GitHub frontend production build](https://github.com/shubhamvivek234/app/actions/runs/38050731115/job/114209586032) passed for `e506747`.
- Both Vercel production deployments report success for the exact application commit: [app](https://vercel.com/findshubhamss-3533s-projects/app/5FvhPakzgX8pVMVKpP6Du9aFSiX8) and [app-fgv2](https://vercel.com/findshubhamss-3533s-projects/app-fgv2/3uWpLhZT5wrDTo1uv1a7qBsS7SL4). GitHub production deployment records are `6980522676` and `6980543093` respectively.
- `https://www.unravler.com/login` and `https://app-fgv2.vercel.app/login` return HTTP 200 and serve the same new `main.b18ac923.js` asset. The public login form renders in a browser; the anonymous `/api/auth/me` HTTP 401 remains expected. Authenticated outreach flows and real provider actions were not exercised. `app.unravler.com` returned 404 at inspection; `app.prosp.ai` is the separate Prosp application. This rollout does not configure the separate future `unravler.io` landing-site domain.

### EC2 rollout and verification

EC2 fast-forwarded from `12f0315` to the exact GitHub release, using the existing checkout and SSH key. All five Python service images were rebuilt sequentially. Previous images remain tagged `rollback-ccf5819-before-jwt2151`. The current MCP image already contained the unchanged release source and was retained.

All three workers reported zero active tasks at inspection before the graceful stop. Background services were stopped with a 180-second grace period; API/MCP passed health checks before workers were restarted. Worker, media worker and video worker each reported ready before the next startup, and beat started last. This is deployment supervision, not a certified all-writer/cache drain for restore activation or custody migrations.

Final verification confirmed:

- API and MCP healthy; all three workers and beat running; zero container restarts in all six services.
- All three expected worker identities answer Celery ping with `pong`.
- All five Python containers run PyJWT 2.15.1 and the newly built service image. Five selected source files, including all four restore-control/helper files and the OAuth account route, match `e506747` byte-for-byte in every Python container.
- Internal `/health` returns HTTP 200/OK. Internal `/ready` returns HTTP 200 with MongoDB, both Redis checks, Firebase admin and R2 storage OK; the existing `auth_password_reset: degraded:custom_link_domain` remains.
- Public unauthenticated outreach campaigns return HTTP 401. The browser CORS preflight from `https://www.unravler.com` returns HTTP 200 with that exact allowed origin and credentials enabled.
- Production `.env` and Compose fingerprints and selected runtime flags match the saved baseline. Live outreach actions and the other previously disabled rollout flags remain false. The pre-existing integration flag remains true; integration activation was not newly authorized or verified.

Metadata-only verification is saved on EC2 at `/tmp/unravler-v254-final-rollout-verification.json`, with a local copy at the same path. No production grants, credential migrations, live-flag enablement, purchases or deliberate AWS/provider pilot calls were performed. The offline helpers still do not establish source completeness, restore real reply suppression or activate execution.

### Outstanding checks and security findings

The full GitHub backend suite is still running at this record's inspection; no full combined green-CI claim is made. The documentation-only follow-up will skip duplicate GitHub workflow runs so it does not cancel the application commit's active backend run. It does not change workflow policy or bypass the existing failed application checks.

The repaired [security workflow](https://github.com/shubhamvivek234/app/actions/runs/38050731122) now runs the formerly malformed checks. TruffleHog passes for this push's range. Python audit reports 72 known vulnerabilities in seven packages in the CI-resolved environment; the separate local pre-final-JWT audit reported 42 in eight packages and is not interchangeable with that CI result. NPM audit reports 136 findings, including three critical dependency-chain findings. These include tooling as well as runtime dependencies and need reachability and upgrade review; no blanket audit fix was applied. Bandit reports existing issues in older upload/media/XML/utility code, so Semgrep remains skipped by that job. Trivy's JWT critical finding is gone, but the API scan still fails on libxml2 `CVE-2026-6653`, with no fixed package version listed in that scan. The security workflow remains red.

Authenticated outside-backup reconciliation/completeness, sender/reply provenance and suppression recovery, transactional new-epoch activation drills, remaining credential/legacy migrations, workload IAM/kernel egress and an actual pilot remain unfinished. Deployment is not certification of those capabilities or a clean security release.

References for the bounded tooling repairs: [PyJWT 2.15.1 changelog](https://github.com/jpadilla/pyjwt/blob/2.15.1/CHANGELOG.rst), [TruffleHog action event-bound behavior](https://github.com/trufflesecurity/trufflehog/blob/main/action.yml), [pip-audit usage](https://github.com/pypa/pip-audit), and [GitHub documentation-only workflow skip behavior](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs).

## Original deployment and synchronization history

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
