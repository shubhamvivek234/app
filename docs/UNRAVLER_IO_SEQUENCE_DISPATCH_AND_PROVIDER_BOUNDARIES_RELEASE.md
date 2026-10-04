# Unravler.io — Sequence dispatch and provider boundaries

Date: 2026-10-02. Local implementation only. Live-action and conditional-launch flags retain disabled defaults. No commit, push, deployment, real provider traffic, purchases or real execution grants were performed.

## Durable selection and execution

The periodic sequence selector persists action intents and sequence jobs in MongoDB before publication. It performs no provider work. A separate publisher sends only workspace/job references; publication failure retains due jobs. Each worker claims one job and one lead with expiring owner tokens, then validates the original enrollment, sender/generation, node, immutable sequence digest/version, campaign authorization revision, state and due occurrence. Stale broker work cannot execute a prospect's newer step.

Condition checks retain their next due occurrence, so a completed poll cannot permanently suppress another check of the same node. Selection and recovery rotate invalid/missing records so a failing prefix does not hide later work. Deferral and completion writes preserve concurrent replies, pauses and replacement owners. Condition-provider reads revalidate job authority through the physical envelope; connection metadata uses the same conditional lead update.

Intents, embedded attempts, legacy outreach_tasks claims and provider-local operation identities remain separate authorities. A claim that expired before possible submission can recover. A possibly submitted action is never reset to pending by timeout or redelivery. Legacy accepted/completed/uncertain/failed records retain their deduplication meaning.

Owning code: outreach/tasks/sequence_dispatch.py, outreach/tasks/sequence_executor.py, celery_workers/tasks/outreach.py.

## Email and billable finder requests

Gmail message POST, Microsoft Graph sendMail POST and Hunter found-only GET now use the shared sender ownership, final permission CAS, physical receipts and MongoDB budgets. Hunter GET is treated as a possible effect because it may consume credits. Endpoints, methods and action kinds are fixed; credentials and query parameters are not written to physical audits.

Permissions last 1–60 seconds and use email_send or email_find. Provider generation binds the sender credential generation plus mailbox provider/user/address/connection identity or encrypted Hunter credential identity. The operator command requires exactly one provider source per grant. Reconnection or credential replacement invalidates a captured provider permission; there is no automatic renewal. Flags, paid access, current campaign/node, lead suppression and original worker context remain independent gates.

Email compares the actual immutable MIME recipient, sender, subject and effective body, including the STOP footer, with the current approved binding. A final approval CAS blocks revoked or changed copy before POST. Gmail acceptance requires HTTP 200 with a nonempty message ID; Graph's legitimate empty-body HTTP 202 records acceptance without inventing an ID. Neither proves delivery. Sender/campaign email_sends limits and existing current-day usage floors apply; the old extra pre-dispatch email increment is removed.

Additional pilot workspace ceilings are 100 email sends/day and 10 finder lookups/day, with tighter sender/campaign/request limits still applying. These are local application ceilings, not vendor-approved safe rates. Reservations rely on MongoDB and fail closed. Proven non-calls can refund action/workspace allowance once; possible calls remain charged.

Finder requests bind the captured normalized LinkedIn handle. Result projection checks original profile, enrollment, node, sender, authorization/version/state and reply/DNC/opt-out/suppression again. A profile edited during lookup cannot receive the old prospect's address. Only found public-source addresses with valid verification can be projected; inferred/unknown addresses remain unavailable.

OAuth exchange/refresh, mailbox synchronization, public proxy health/inventory and voice/model vendors remain outside this send/finder envelope. Refresh mutations independently match their captured connection identity and nonce; reconnect clears old leases so an old refresh cannot overwrite or scrub new credentials. This change does not establish universal egress isolation.

Owning code: outreach/core/provider_boundary.py, outreach/core/provider_operations.py, outreach/core/mailbox_delivery.py, outreach/core/email_finder.py, outreach/core/mailbox_connection.py, outreach/ops/pilot.py.

## Receipt repair and ownership cleanup

Stable provider-local operations preserve ambiguous sends/lookups instead of repeating them. Exact matching response_received evidence can repair the operation and its original logical intent/task without HTTP. Repair binds tenant, sender, original owner, source, provider generation, logical operation and original sequence context, and cannot override a human resolution.

Repaired email acceptance uses the physical receipt's original completed_at as accepted_at. Replies arriving between provider acceptance and local repair remain matchable. Finder receipt repair can project onto the matching outcome-paused lead while preserving original profile/enrollment/revision and suppression fences. Existing campaign pauses and permission latches remain; repair does not reauthorize or resume campaigns.

A physical response that committed before an acknowledgement failure remains response_received. Cleanup can clear only the same owner's token backed by that exact received receipt. Unknown/in-flight tokens block sender release. Projection reconciliation is recorded after idempotent local cleanup so a cleanup fault remains recoverable. Recovery due times rotate missing or faulting records.

Owning code: outreach/core/execution_recovery.py, outreach/core/request_guard.py, outreach/core/sender_execution.py.

## Verification and limits

- 563 outreach backend tests pass, including 13 isolated real MongoDB concurrency/fault tests and 5 real Redis/Celery tests.
- Four Redis tests SIGKILL a worker before submission, after possible submission, after a fake provider call and after saved logical acceptance, then verify real unacknowledged-message redelivery. A fifth verifies retained publication while Redis is unavailable and successful publication after a disposable Redis server starts.
- The process-kill harness exercises the production sequence job/outbox protocol with a fake provider counter. It does not exercise physical HTTP, provider receipt custody or token cleanup across a real process kill. Separate full sequence/provider fault tests cover operation acknowledgement loss, committed physical receipt acknowledgement loss, sender cleanup faults and exact receipt repair.
- The isolated broker visibility timeout is three seconds. Tests advance isolated database leases to model expiry; this does not establish production visibility/lease timing or broker durability across a server data-loss event.
- Provider/dispatch modules have 86% combined statement coverage, each above 80%. Python compilation, medium/high Bandit and whitespace checks pass. Final review applies to this local disabled-live scope.
- Frontend is unchanged in this slice; the prior slice's 79 frontend tests and production build evidence are retained, rather than claimed as rerun here.

Tests create random local databases/queues with fake values. No real credentials, grants, paid calls or external provider requests are used. Disposable services are stopped after verification.

## Cutover and next work

Deploy only after a separate reviewed release decision. Drain legacy sequence batch workers before switching to selection-only scheduling, provision/verify sequence/provider/recovery indexes from db/indexes.py, retain existing action/email records, and confirm the sequence publisher plus per-job worker are running. Keep all live flags disabled during rollout. Old batch messages run the selection-only entry point; new messages carry references. Do not remove legacy deduplication records or flush possibly submitted work to make a migration appear clean.

Next implementation: complete drained human resolution/read-back for unknown manual actions, then connection-finalization repair and bounded credential custody. Strict ordering across independent authority documents, outreach erasure/retention, offline voice preparation, credential/route isolation and restore fencing remain release work. Purchased IPRoyal seats and the mailbox pilot still need real verification before any live-action decision. Automated payment collection/proxy procurement remains deferred.
