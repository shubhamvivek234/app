# Unravler.io v2.81–v2.82 deployment checkpoint

Updated: 2026-10-18 IST. **Frontend deployed; backend awaiting the new EC2 address.**

Application commit [`b29a734`](https://github.com/shubhamvivek234/app/commit/b29a734aa39f35648c104224dbd2be99636a03ac) is pushed to `origin/main`. It contains the reviewed graph-update and deletion recovery slices and their tests/documents. Unrelated `.gitignore`, Prosp documents, skill files and nested worktree changes are excluded. Implementation evidence remains in the [graph recovery](UNRAVLER_IO_TEMPLATE_GRAPH_RECOVERY_RELEASE.md) and [deletion recovery](UNRAVLER_IO_TEMPLATE_DELETION_RECOVERY_RELEASE.md) reports; their local-only statements describe the implementation checkpoint before this rollout.

## Frontend

Both exact-application-commit Vercel checks succeeded:

- [app production deployment](https://vercel.com/findshubhamss-3533s-projects/app/Hfz3WazWKsAFc33mwHaUw3QconWF).
- [app-fgv2 production deployment](https://vercel.com/findshubhamss-3533s-projects/app-fgv2/J8hz5SahKGVzbWdcxC1CV3FsB6Ae).

Both `https://www.unravler.com/login` and `https://app-fgv2.vercel.app/login` return HTTP200. On both sites `/static/js/733.27dc18e6.chunk.js` returns200, contains both original sequence-update/deletion confirmation flows, and exactly matches the locally verified asset SHA256 `9d3d7cd50a2f75c789c9a6f302edddfcdec443cc556711faabff668074504ea7`.

## Backend and required input

The user changed the deployment key to `/Users/shubham/Downloads/unravler-ec2-key.pem`. The key exists and local permissions are restricted to0600; its contents were neither printed nor committed. An SSH connection to the previously recorded `ubuntu@51.20.210.184` timed out on port22. No backend checkout, containers, flags, secrets or production data were modified.

The new EC2 public IP/hostname and SSH username are required before rollout can continue. A question is pending in this chat; `ubuntu` is only the previous username, not a verified new-target identity. Once supplied, inspect the actual server/checkout/Compose setup, preserve configuration, supervise background-worker shutdown and matching sequential image rollout, start beat last, then verify health/readiness, worker pings, source hashes and unchanged execution flags. Do not treat frontend success as backend availability of the new receipt APIs. An older backend can return unavailable/unconfirmed outcomes until its matching rollout completes.

## Checks and limits

Local approved verification:5,358 distinct backend passes,514 frontend checks,44 synthetic browser journeys and production build. [Remote CI](https://github.com/shubhamvivek234/app/actions/runs/39117618638) frontend build and outreach browser contracts pass; broad backend and native database jobs were still running at this checkpoint.

The [security workflow](https://github.com/shubhamvivek234/app/actions/runs/39117618774) fails NPM dependency audit and Trivy container scan. Trivy reports critical libxml2 `CVE-2026-6653`; the same finding was recorded in the older v2.54 deployment report. Python dependency audit, SAST and secret scan pass in this run. No clean-security or combined-green-CI claim is made, and no security check is disabled. No authenticated/live outreach, integration activation, grant, migration, provider/AWS pilot or purchase was performed.
