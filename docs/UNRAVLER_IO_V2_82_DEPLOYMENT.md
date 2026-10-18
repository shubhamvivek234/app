# Unravler.io v2.81–v2.82 deployment checkpoint

Updated: 2026-10-18 IST. **Frontend and backend deployed; API, MCP, workers and Beat run the rebuilt release images.**

Application commit [`b29a734`](https://github.com/shubhamvivek234/app/commit/b29a734aa39f35648c104224dbd2be99636a03ac) is pushed to `origin/main`. It contains the reviewed graph-update and deletion recovery slices and their tests/documents. Unrelated `.gitignore`, Prosp documents, skill files and nested worktree changes are excluded. Implementation evidence remains in the [graph recovery](UNRAVLER_IO_TEMPLATE_GRAPH_RECOVERY_RELEASE.md) and [deletion recovery](UNRAVLER_IO_TEMPLATE_DELETION_RECOVERY_RELEASE.md) reports; their local-only statements describe the implementation checkpoint before this rollout.

## Frontend

Both exact-application-commit Vercel checks succeeded:

- [app production deployment](https://vercel.com/findshubhamss-3533s-projects/app/Hfz3WazWKsAFc33mwHaUw3QconWF).
- [app-fgv2 production deployment](https://vercel.com/findshubhamss-3533s-projects/app-fgv2/J8hz5SahKGVzbWdcxC1CV3FsB6Ae).

Both `https://www.unravler.com/login` and `https://app-fgv2.vercel.app/login` return HTTP200. On both sites `/static/js/733.27dc18e6.chunk.js` returns200, contains both original sequence-update/deletion confirmation flows, and exactly matches the locally verified asset SHA256 `9d3d7cd50a2f75c789c9a6f302edddfcdec443cc556711faabff668074504ea7`.

## Backend and required input

The user changed the deployment key to `/Users/shubham/Downloads/unravler-ec2-key.pem`. The key exists and local permissions are restricted to0600; its contents were neither printed nor committed. The previous `ubuntu@51.20.210.184` target timed out on port22. The supplied new Sydney target, `ec2-user@3.104.181.230` (`ec2-3-104-181-230.ap-southeast-2.compute.amazonaws.com`), accepts the key and opens an Amazon Linux2023 shell. Docker was restarted after its control API stalled; all nine expected Unravler containers came back. The `/opt/socialentagler` checkout was fast-forwarded from `1907bd2` through `cf5f8d4` to `1f25b5a`, preserving its local `docker-compose.yml` modification and `backend/.env`. Commit `1f25b5a` adds `.dockerignore`, excluding the unused3.2GiB frontend dependency tree, Git state, caches and environment files from backend image contexts. The first Compose BuildKit API build returned `DeadlineExceeded`; the legacy fallback stalled for several minutes, consuming the 913MiB host's memory and swap until it was cancelled. A second normal Compose build with the reduced context still made no Docker-layer progress within two minutes and was cancelled. The current containers therefore still run the pre-release images; no application container replacement, flag, secret, provider or data mutation was performed.

Before rollout can continue, restore a responsive Docker build service and provide sufficient host capacity for image construction, such as temporarily resizing this EC2 instance to at least2GiB RAM or building and publishing the images elsewhere for a pull-only rollout. Once capacity is available, rebuild the API/MCP/worker images one at a time, replace API and MCP, then workers and Beat last, and verify health/readiness, worker pings, source hashes and unchanged execution flags. Do not treat frontend success, the updated checkout, or the build-context fix as backend availability of the new receipt APIs. Existing pre-release containers can return unavailable/unconfirmed outcomes until their matching images are running.

## Verified backend rollout

The preceding backend paragraphs record the earlier failed build attempts. They were superseded after the EC2 instance was resized to1.9GiB RAM. The `/opt/socialentagler` checkout was fast-forwarded to `435905a`, preserving its local `docker-compose.yml` modification and `backend/.env`. The `.dockerignore` in `1f25b5a` reduced the API build context from the unused3.2GiB frontend dependency tree to181kB and excludes Git state, caches and environment files.

API, MCP, worker, worker_media, worker_video and Beat images built sequentially. API and MCP were recreated first and report healthy; all worker logs report ready; Beat was started last. MongoDB and Redis report healthy. The API `/health` endpoint returns `{"status":"ok"}`. Its `/ready` endpoint retains existing R2 and password-reset custom-link-domain warnings, while MongoDB, Redis queue/cache and Firebase admin checks pass. `OUTREACH_LIVE_ACTIONS_ENABLED=false` and `OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED=false` are verified inside the API container. The public `/health` route returns the intentionally blocked403 response. No authenticated outreach, integration activation, grant, migration, provider/AWS pilot or purchase was performed.

## Checks and limits

Local approved verification:5,358 distinct backend passes,514 frontend checks,44 synthetic browser journeys and production build. [Remote CI](https://github.com/shubhamvivek234/app/actions/runs/39117618638) frontend build, outreach browser contracts and native database contracts pass; its broad backend test job was cancelled, so this deployment does not claim a complete remote-green CI run.

The [security workflow](https://github.com/shubhamvivek234/app/actions/runs/39117618774) fails NPM dependency audit and Trivy container scan. Trivy reports critical libxml2 `CVE-2026-6653`; the same finding was recorded in the older v2.54 deployment report. Python dependency audit, SAST and secret scan pass in this run. No clean-security or combined-green-CI claim is made, and no security check is disabled. No authenticated/live outreach, integration activation, grant, migration, provider/AWS pilot or purchase was performed.
