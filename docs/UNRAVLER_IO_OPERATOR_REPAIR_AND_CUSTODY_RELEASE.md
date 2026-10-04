# Unravler.io — Operator repair and pending credential custody

Date: 2026-10-02. Local implementation only. Live-action and conditional-launch flags retain disabled defaults. No commit, push, deployment, purchases, real execution grants or external provider requests were performed.

## Manual action review

The private operator CLI can inspect an uncertain manual Engage/reply job and record a drained review against its exact snapshot digest. Decisions cover every uncertain stage: confirmed_sent, not_sent_stop or use_receipt. The review binds workspace, sender, original content/binding, stage, physical request identity, credential generation, original owner and logical operation. Changed or contradictory evidence is refused.

Human confirmation becomes human_confirmed with human_assertion provenance. It does not fabricate a provider receipt, an inbox sent message, liked_at/commented_at, verified engagement counts, or warm-up eligibility. A genuine matching received acceptance uses the original transport timestamp and can repair its reporting exactly once. Already accepted stages retain their evidence; all remaining unattempted stages are cancelled. Reviewing an interrupted like cannot automatically send the remaining comment.

Permission is revoked before resolving a physical request or releasing its owner/token. Resolving jobs hold their target and block new grants until cleanup finishes. The saved review resumes database-only repair after an interruption; it never performs HTTP, renews permission, or resumes a campaign. Inbox polling recognizes resolving/resolved states and shows recorded review separately from a confirmed sent message.

Owning code: outreach/core/manual_resolution.py, outreach/core/manual_actions.py, outreach/core/execution_permission.py, outreach/tasks/manual_actions.py, outreach/api/inbox.py.

## Installation fence and custody deadline

New connection jobs stamp installation_protocol=2, the original capture time and a custody deadline no later than 15 minutes after capture. Pending verification grants end at that deadline, and the physical verification boundary rejects expired custody. Finalization cannot reset that clock.

Preparation writes prospective job metadata and an account-local prepared fence without installing usable new credentials. Reconnect preparation checks the captured sender identity/generation and current encrypted material. Installation matches the exact account fence, job, owner, prospective generation, original base generation and live custody deadline. The final MongoDB account update checks server $$NOW; cached worker values cannot bypass a closed fence or a delayed write crossing the deadline. Completion independently rejects an expired custody latch and uses the same server deadline.

The 60-second cleanup task runs with live flags disabled. It scrubs overdue persisted pending secrets, closes the original account fence, and scrubs an installed exact generation when needed. Install and close contend on the same account document. Paid expiry also closes fences and scrubs pending/session secrets. Changed account generations stay quarantined; they are never overwritten or erased by an old repair.

This is an application deadline plus a cleanup service objective while MongoDB and the cleanup worker are available, with bounded backlog. It is not guaranteed deletion during an outage, erasure of cached process memory, or universal credential custody. KMS/workload identity, process isolation and restore fencing remain separate work.

Owning code: outreach/core/connection_repair.py, outreach/api/connection_jobs.py, outreach/core/managed_proxy.py, outreach/core/paid_access.py, outreach/core/request_guard.py, celery_workers/tasks/outreach.py.

## Drained connection repair

An operator can retain_installed only when the exact installed identity, generation, encrypted-material digest, proxy binding, seat and current paid/provider terms still match. This retains an existing verified session; it cannot restore credentials from pending bytes. Permission stays latched and affected campaigns stay paused.

stop_and_scrub closes the exact original fence and removes its usable credentials. A possibly or definitely installed IP/seat remains bound through the provider term. Only a proven never-installed reservation with this job's reservation_job_id may be released. Resource records belonging to another job survive. Releasing a local reservation does not cancel an IPRoyal order or remove provider charges.

Legacy jobs without an installation fence retain ambiguous assets for drained inspection. Missing custody metadata causes pending secret scrubbing and quarantine, rather than indefinite pending retention or an invented non-installation proof. A legacy exact installed generation can be stopped under explicit inspection; a replacement generation is refused. A v2 pre-install job can release its exact new reservations only after a stopped-job CAS proves preparation did not occur and no account exists.

Original pending-job verification reads can be resolved as read_interrupted after draining; unrelated physical requests retain their own holds. Saved repairs retry account/resource/lock cleanup without provider calls. A terminal cleanup retry never revisits a newer account generation. Known successful connection jobs also persist a cleanup marker, so interrupted lock deletion resumes without touching installed or replacement credentials. An unfinished retain decision may be explicitly changed to stop_and_scrub with a fresh digest, new drain assertion and preserved repair_history; the reverse transition is refused.

Unresolved evidence omits the TTL-indexed created_at. Terminal retention resumes only after cleanup completes. An immutable failed review remains auditable; do not delete history or flush possibly submitted work to force a clean rollout.

## Private operator commands

Run on the trusted backend host with its normal database configuration. Inspection is read-only and prints sanitized metadata and review_digest, never pending/session ciphertext or proxy credentials. Independently stop and drain the sender's workers before a resolve command; the literal flag records that operator assertion and does not drain workers itself.

```bash
.venv/bin/python -m outreach.ops.pilot inspect-manual-review --workspace WORKSPACE --job JOB
.venv/bin/python -m outreach.ops.pilot resolve-manual-review --workspace WORKSPACE --job JOB \
  --operator OPERATOR --review-digest DIGEST --decision comment=not_sent_stop \
  --evidence 'Describe the independent inspection of the original action.' \
  --workers-drained I_PAUSED_AND_DRAINED_SENDER_WORKERS

.venv/bin/python -m outreach.ops.pilot inspect-connection-repair --workspace WORKSPACE --job JOB
.venv/bin/python -m outreach.ops.pilot resolve-connection-repair --workspace WORKSPACE --job JOB \
  --operator OPERATOR --review-digest DIGEST --decision stop_and_scrub \
  --evidence 'Describe the exact-generation, installation and resource inspection.' \
  --workers-drained I_PAUSED_AND_DRAINED_SENDER_WORKERS
```

Repeat the same saved decision to finish a database interruption. Inspect again before changing an unfinished retain decision to stop. Evidence is 20–2000 characters. Do not enter cookies, OAuth tokens or proxy credentials in evidence or CLI arguments. These commands are private operator tools; there is no new customer repair/write endpoint or automated operator decision.

## Verification and rollout limits

614 distinct outreach backend tests pass: the final suite passes 609 with the 5 opt-in broker drills separately passing. This includes 17 isolated real MongoDB tests and a successful migration from the older partial manual-action index to manual_active_target_v2. The 79 outreach frontend tests, production build, Python compilation, medium/high Bandit and whitespace checks pass. Repair modules have 88% combined statement coverage (connection repair 88%, manual resolution 89%). Final code review approves the bounded local disabled-live slice. Existing frontend dependency/Tailwind/source-map/bundle warnings remain. New isolated MongoDB tests cover actual account install/expiry contention, a delayed installation update crossing server time, manual assertion/projection idempotency and migrated uniqueness while a target is resolving. Fault tests cover lost acknowledgements, saved-review recovery, replacement generations, pending grant expiry, legacy quarantine and reservation ownership. Existing Redis/Celery SIGKILL drills cover the dispatch/outbox protocol with fake effects; physical provider receipt/token process-kill drills remain outstanding.

Before any deployment, separately drain older connection/manual workers, verify indexes (including manual_active_target_v2 and custody/repair scan indexes), inspect unresolved old jobs/assets, and confirm the cleanup/recovery schedules are running. Keep live flags disabled. The assertion flag cannot substitute for drain evidence; older workers do not gain the new installation fence merely because documents or indexes were updated.

Next implementation: physical provider receipt/token process-kill drills, then strict authority ordering and outreach erasure/retention. Offline voice preparation, credential/route isolation, restore fencing, purchased IPRoyal seat checks and the mailbox pilot remain release work. Automated payment collection/proxy procurement remains deferred.
