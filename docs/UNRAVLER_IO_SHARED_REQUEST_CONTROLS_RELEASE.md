# Unravler.io — Shared request controls release

Date: 2026-10-02. Baseline: `2187946`, plus the uncommitted [execution foundation](UNRAVLER_IO_EXECUTION_FOUNDATION_RELEASE.md). This second implementation slice is local only. No commit, push, deployment, purchase, execution grant or live provider call was made. Existing live-action defaults remain disabled.

## Result

LinkedIn reads and mutations through the Voyager/session adapters now share MongoDB request budgets, sender ownership and short-lived operator permission. A temporary rejection proven to occur before transport can defer safely. An attempted mutation with an ambiguous result retains evidence and sender ownership, stops permission and cannot be replayed automatically.

| Control | Owning implementation | Local behavior |
|---|---|---|
| Shared budgets | `outreach/core/request_guard.py` | Atomic sender/workspace counters for hourly, daily and action caps; reserved sync/verification capacity; deny on authority failure |
| Execution permission | `outreach/core/execution_permission.py` | Explicit grants lasting 1–60 seconds, bound to credential generation and allowed sources; expiry and stop latch enforced from authoritative sender record |
| Shared sender ownership | `outreach/core/sender_execution.py` | Sequence, sync, search, inbox reply, Engage and verification use the same authority; final ownership/permission transition is one MongoDB document |
| Physical evidence | `outreach/core/request_guard.py` | Secret-free request identity, endpoint digest, source, action, generation, owner and timestamps before transport; response status or unresolved outcome afterward |
| Adapter coverage | `outreach/engine/voyager_client.py`, `outreach/engine/session_authenticator.py` | Guard every LinkedIn HTTP subrequest, including profile resolution, pagination and `/me`; require the actual configured proxy to match the envelope |
| Durable search scheduling | `celery_workers/tasks/outreach.py`, `outreach/api/leads.py` | Store page due times and owner tokens; 30-second publisher retries identifiers after broker failure; stale page/reaper writes are fenced |
| Pending verification | `outreach/api/connection_jobs.py`, `celery_workers/tasks/outreach.py` | Wait for job-bound verification permission before proxy health/decryption; preserve encrypted pending values and reservations on known denials; 30-second publisher retries due jobs |
| Operator controls | `outreach/ops/pilot.py` | Grant/stop permission, list unresolved physical requests and record a drained-worker human assertion; no automatic resume or grant from outcome review |

Sequence execution keeps its existing outer intent/attempt owner and supplies a preflight validator for each physical subrequest. Standalone operations acquire the same sender record. Final permission and owner checks share a single atomic MongoDB transition, followed by an expiry check with no intervening asynchronous work before transport. Campaign, entitlement, lead/DNC, job and asset checks remain separate document reads; this release does not prove strict ordering across all those authorities.

## Budget and retry semantics

- All HTTP subrequests count toward physical capacity. Default local ceilings are 120 requests/hour and 1,000/day, with 20% reserved for sync/verification. These values are server configuration, not LinkedIn-approved limits. Sender policies may tighten them.
- Actual mutation calls share the sender's configured invite/message/like/comment/voice/visit limits across sources; campaign limits may tighten them further. Voice is classified separately from messages despite the shared messaging endpoint.
- Current-day legacy action counts seed the new action counters as floors, including when an earlier verification/read initialized that day's budget. Drain old workers before cutover; legacy writers must not continue alongside the new authority.
- Physical capacity stays conservatively charged after a reservation even if transport is later denied. A unique per-call reservation lets proven non-calls refund business action allowance at most once; it cannot refund a prior sent operation.
- Engage post actions and inbox replies have stable physical operation identities. Only an explicit `not_submitted` record can be reclaimed with owner/status fencing, fresh reservation and preserved non-call history. Preparing, received, unresolved and human-resolved outcomes remain blocked from replay.
- Mutation timeout, cancellation, interrupted evidence recording, ambiguous success, HTTP 408/429 or 5xx retain possible-submission evidence and latch permission. A hard 30-second physical transport deadline is enforced. Reads that fail normally release ownership; a process crash may require drained review of the retained token.
- A permission grant is manual and expires within 60 seconds. There is no automatic health-monitor renewal or content-approval enforcement in this slice. Broker references and reporting projections never authorize execution.

The old `RateBudget` interface now delegates storage to the MongoDB budget; it has no process-memory fallback. Unsupported automatic invitation withdrawal returns no completed actions and does not fabricate withdrawn lead state. Email, email-finder/model providers and public proxy-health/provider inventory calls are outside this LinkedIn envelope.

## Connection finalization and custody

Queued/running verification retains the existing 15-minute cleanup bound. Broker failure and permission deferral preserve the pending setup instead of discarding it. The worker checks due time, job ownership, paid access, slot, lease, inventory and country; the physical verification boundary rechecks reserved capacity and proxy binding.

After the final awaited checks, an owner/status CAS moves the job to `finalizing` before writing account credentials. The ordinary stale-job and entitlement cleanup may release only pre-finalization jobs. Completion must match the finalizing owner. Pre-finalization failure releases reservations only when its own failure transition succeeded.

A write whose acknowledgement is lost may already have installed credentials. Such failures retain the IP lease, sender slot, connection lock and finalization generation; scrub pending job secrets; revoke permission; and require drained operator repair. New grants reject any unresolved finalizing job, even with explicit unlatching. Paid expiry after the account write scrubs only that exact new generation.

Finalizing jobs move original `created_at` to `custody_started_at` and remove the TTL-indexed field. This preserves unresolved repair evidence. Known completion restores the original TTL timestamp. A process crash during finalization may retain encrypted pending values until operator repair; automatic finalization recovery and a dedicated repair command/UI are still outstanding. Do not claim the 15-minute queued/running cleanup covers finalizing custody.

Drained repair must inspect the job's exact credential generation, account identity, paid coverage and bound IP, record the operator decision/evidence, and scrub or retain that generation deliberately. Release only proven pending reservations; keep connected leases through provider expiry. Finish the job/lock with job and owner fences, restore terminal retention metadata, and keep execution stopped. Never erase the job or release its IP simply because its worker disappeared.

## Verification

- **470 outreach backend tests pass**, including **9 real local MongoDB concurrency/fault tests**. Each real-database test uses an isolated random database and fake provider transport.
- Tests cover shared limits/ownership, concurrent reservations, legacy counter floors, final revocation/expiry, actual proxy mismatch, action classification, ambiguity/timeout, cancellation, non-call refunds/reclaim, replay protection, durable broker-failure simulation, stale verification owners and lost credential-write acknowledgement.
- **91% statement coverage** across the two new request/permission modules (permission 90%, request guard 91%). The prior foundation's seven-module coverage result remains in its historical report.
- Python compilation, medium/high-severity Bandit and whitespace checks pass. Final Python/security/concurrency review approves this bounded release with live actions disabled.
- No frontend files changed in this slice. The earlier foundation validation passed 75 outreach frontend tests and the production build with existing warnings; those checks were not repeated here.

No real LinkedIn/IPRoyal/mailbox traffic, production index migration, broker restart/process-kill drill, kernel route isolation or restore drill was performed. Tests do not establish provider delivery or production readiness.

## Cutover prerequisites

1. Keep live flags disabled and drain all old sender workers and API-triggered requests. Older code does not enforce this permission protocol; mixed live versions are unsupported.
2. Verify physical-request, due-job, permission, sender-ownership and existing legacy-action indexes; resolve every index-creation failure before rollout. Preserve legacy action evidence and current-day counter floors.
3. Retain uncertain physical/logical records and finalizing connection jobs. Do not clear ownership, TTL fields or credential generations to bypass review. Pause/drain the affected execution before recording a human resolution.
4. Test pending-job grants (`verify` only, generation `pending:<job_id>`), then a separate explicit grant for the successfully connected generation. A pending verification grant never carries over to the connected account.
5. Keep rollback stopped and retain all evidence. Do not run old workers live against restored or newly permission-gated state.
6. Complete the remaining operational requirements before any separate live-action release decision.

## Next implementation

1. Implement policy-bound content approval and reusable outcome/repair projections for non-sequence mutations and voice stages. Move remaining API-triggered Engage transport to durable worker execution; a shared guard does not establish process isolation.
2. Add a separate action-intent publisher, complete email/finder/provider boundaries, and exercise real broker/process crash and reply/authorization race drills.
3. Prove required cross-authority ordering; implement finalization repair/custody bounds, credential migration, egress/IPv6 isolation and restore fencing. Verify retention and erasure for existing and new outreach records: the inspected `celery_workers/tasks/gdpr.py` erasure collection list currently omits outreach collections.
4. Independently verify purchased IPRoyal seats, route identity, LinkedIn parser coverage and the mailbox pilot. Automated billing/procurement remains later work; manual verified-invoice provisioning is unchanged.
