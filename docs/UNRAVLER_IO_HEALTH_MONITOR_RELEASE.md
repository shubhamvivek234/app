# Unravler.io passive verified-evidence health control — v2.34

Date: 2026-10-08. Thirty-third implementation slice. Local work, uncommitted and undeployed. Foundations through v2.22 remain the deployed baseline at `04ca28b5d1dd7bd213ea67e951970e19fd93bdf3`; later local slices are not claimed deployed. Production configuration and flags were not changed.

## Result and scope

An existing verified LinkedIn sender can have a finite private operator-authorized renewal control. The 30-second monitor reads retained original evidence; it makes no network request and opens no cookie/proxy/key. Arming grants nothing. Renewal continues only the exact sources and generation of a current explicit unlatched permission and never resumes a campaign, activates an integration or clears a stop latch.

This is deliberately a short passive evidence window, not continuous health probing. Original parsed-identity proof expires after 90 seconds even when an operator window is longer. A stopped control never automatically reopens after fresh evidence appears. Older healthy labels/timestamps cannot substitute for original proof. New live probes, challenge/cohort trend thresholds and restoration epochs remain separate work.

## Original proof and deadlines

Normal connection verification now records its observation immediately after the existing identity parser returns, then binds it to newly installed generation/member/cookie material and assigned proxy transport. Evidence is installed with the existing credential write. The monitor requires the exact completed unrepaired connection job, closed verified-install fence/member and installed credential digest, native UTC observation, original transactional HTTP 200 read receipt within ten seconds before that observation, current credential/proxy binding and live/non-mock configuration. No generic read/status success creates proof by itself.

Current paid access, modern tenant-owned provider inventory and expiry, lease/country, sender slot, managed Webshare original proof where applicable, workspace openness, sender status and explicit original permission are revalidated. Unresolved physical/manual/action work, pending connection/finalization/locks, malformed authority or bounded-capacity gaps deny. A current matching in-flight physical owner with a live lease defers without changing its permission or token; an orphan/unknown outcome requires review.

An operator window is 1–900 seconds. Each permission lasts at most 60 seconds and ends at the earliest of window expiry, observation plus 90 seconds, paid expiry or proxy expiry. Source selection excludes pending verification, email send and finder work. Runtime flag/configuration withdrawal denies control-derived permission after the root read and through a pure post-commit dispatch check before physical request entry. A submitted request can already have external effects; its original evidence/reconciliation path remains authoritative.

## Ordering and recovery

Arm/tick/stop use snapshot/majority workspace suppression ordering. Matching authority rows are read-fenced, permission writes compare the current full row and revision, and root/projection/permission updates commit together. An aborted write/final deadline check rolls back the grant. Concurrent duplicate ticks renew once; a saved tick sees the next due time. Exact saved arm retries return historical status rather than recreate permission. Changed generation/revision/source decisions obsolete the old controller without stopping newer authority.

A current negative stop latches permission and pauses the bounded matching active/warming campaign scan. Physical owners/tokens/budgets/unknown evidence are retained. Scan overflow reports `campaign_pause_scan_complete=false`; the current permission remains stopped and extra campaign inspection is required. Failures receive sanitized logging and exact still-armed/current-due scheduling backoff so a failed prefix cannot monopolize each scan. Standalone Mongo denies without fallback. Raw/older writers that ignore shared guard/revision rules remain outside this protocol guarantee.

## Operational controls

`OUTREACH_HEALTH_MONITOR_ENABLED=false` is present in the environment example and shared Compose environment. It enables no initial permission by itself and is ineffective without the existing live action gate/non-mock authority. The periodic reference-only outreach task runs every 30 seconds and checks shutdown before opening the database. With no armed roots it performs no renewal; flags-off current roots stop, and erasure explicitly stops roots before purge.

Private commands accept bounded references and SHA-256 review/evidence digests, never cookies, proxy URLs, provider keys, replay or campaign activation inputs:

- Inspect: `python -m outreach.ops.health_monitor inspect --workspace WORKSPACE --sender SENDER`
- Arm a reviewed current inspection: `python -m outreach.ops.health_monitor arm --workspace WORKSPACE --sender SENDER --operator OPERATOR --evidence-digest REVIEW_EVIDENCE_SHA256 --review-digest INSPECTION_DIGEST --window-seconds 300`
- Stop: `python -m outreach.ops.health_monitor stop --workspace WORKSPACE --control CONTROL_SHA256 --operator OPERATOR --evidence-digest REVIEW_EVIDENCE_SHA256`

These commands install no configuration or initial grant. They run on a trusted operator host, not a public API. Fleet/configuration policy cutover requires separately identified operator control and uniform writer/cache drain. Retain original evidence independently. Exact inspection digest or a changed/stopped permission requires fresh review; a longer operator window cannot extend original proof freshness.

Startup removes control evidence TTLs before strict index builds. `health_sender_active_v1` permits only one armed control per workspace/sender; conflicting legacy roots fail startup and require review. There is no TTL expiry/recreation of authorization history. Erasure classifies the collection, stops armed roots and preserves only minimal hashed sender/generation/operator/evidence/window/outcome provenance. Closed tenants cannot recreate permission through a control.

## Verification

Final focused check: 82 passed (56 service/worker, 9 CLI and 17 actual Mongo), including actual Mongo cases with default naive-UTC BSON, duplicate ticks, native proof, rollback, stopped/replaced/closed authority, strict TTL/index failure, erasure and standalone denial. The two added actual RequestEnvelope post-commit flag/policy regressions passed both separately and in the final focused run and proved the physical factory was never called; the request was recorded not submitted. The 23.67-second focused run measured combined new service/CLI statement coverage at 97% (service 98%, CLI 96%). Independent code review passed with no remaining HIGH/CRITICAL findings after fixing the flag-change race; 65 service/CLI checks and two isolated boundary regressions independently passed.

Final normal backend run: **2,521 passed, 44 historical opt-in drills skipped, 2 warnings, 769.46 seconds**. The two post-commit cases were added after broad collection and also passed separately and in the final 82-case focused run: **2,523 distinct current backend checks** (2,503 outreach +20 account/auth companions), with all 82 new cases passing. No failed case was excluded or crash timeout changed. Initial new test fixture errors (literal array CAS expectations, parser mock recursion, fence counters, closed guard insertion and missing erasure owner setup) were corrected before clean final runs; shared fakes were not changed for this slice.

Compile, medium/high Bandit, both Compose validation targets and diff whitespace checks pass. Existing dependency deprecation and unset example Compose environment warnings remain. Optional ruff/black/mypy tools are unavailable. Frontend unchanged; previous 99 tests/production build are historical, not rerun for this slice. No new Redis/SIGKILL crash, provider health probe, AWS, production or physical kernel egress test is claimed.

Repository/Desktop v2.34 specs, runbook and 33 linked release reports byte-match; all 122 spec links resolve. Eight pre-edit repository/Desktop document copies are retained in `/tmp/unravler-docs-before-v2-34-20261008` (0700 directory/0600 files). Owned Mongo PID30239 and its exact command/root were verified before termination; no temporary database remained. Owned process/storage and explicit final test directory were removed, and ports27028/27029/6389 are closed. No Redis was started. Cleanup proof: `/tmp/unravler-v234-cleanup.json` (0600). Existing unrelated dirty files/worktrees and repository coverage cache were preserved. Final independent source/contract and log/copy/link/backup/process/storage/port audit approved with no HIGH/CRITICAL findings or evidence discrepancies. Zero database/no-Redis conclusions use the primary recorded cleanup proof; the final reviewer independently confirmed process/storage absence and closed ports without starting services.

## Files and remaining work

New service/private CLI and three test modules: `outreach/core/health_monitor.py`, `outreach/ops/health_monitor.py`, `tests/test_outreach_health_monitor{,_ops,_mongo}.py`. Wiring: `outreach/core/execution_permission.py`, `celery_workers/tasks/outreach.py`, `db/indexes.py`, `outreach/core/erasure.py`, `backend/.env.example`, `docker-compose.yml` (production target is the existing symlink).

Next: deployment restore-epoch fencing and operational restore checks; then independently authorized budgeted live health observations and cohort/challenge controls. Missing-original-fact Webshare adoption, remaining shared-provider credentials, unproven/different-key source or older synchronous Studio/artifact evidence, explicit integration activation and purchased-seat/mailbox/voice end-to-end pilot evidence remain outside this release. No commit, push, deployment, production grant/flag change, real AWS/provider call or purchase occurred.
