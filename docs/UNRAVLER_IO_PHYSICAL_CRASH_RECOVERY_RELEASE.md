# Unravler.io — Physical request crash recovery

Date: 2026-10-02. Local implementation and isolated verification only. Live-action and conditional-launch flags retain disabled defaults. No commit, push, deployment, purchases, real execution grants or external provider requests were performed.

## Result and correction

The new process-kill suite exercises production ManualActions, VoyagerClient, SequenceExecutor, ProviderEnvelope, RequestEnvelope and database recovery through real MongoDB, Redis/Celery redelivery and local TCP HTTP. A missing durable response remains held even when the local endpoint accepted the request. An exact saved acceptance repairs the original result and reporting without a second request. Cleanup of an old completed job cannot release a replacement owner's request token.

The tests exposed one recovery gap: a manual stage could be marked possible_submission, then its physical audit inserted as preparing, before a worker was killed. Recovery correctly held the action, but drained operator review rejected the preparing audit and could not close it.

Preparing physical mutations now allow only not_sent_stop after explicit draining and review. Preparing reads allow only read_interrupted. Neither can be asserted confirmed_sent. Resolution retains original_status=preparing and human_assertion provenance, revokes permission before clearing any exact original-owner/request token, and does not regrant, resend, refund a possibly consumed budget, create a sent message, or qualify verified engagement. The existing snapshot digest and physical identity checks still apply to manual review. A replacement owner/token survives the old review.

Owning code: outreach/core/manual_resolution.py and outreach/core/execution_permission.py. Regression tests: tests/test_outreach_manual_resolution.py.

## Physical crash matrix

| Production path | Kill points | Cases |
|---|---|---:|
| Manual LinkedIn reaction | Job preparing; physical audit preparing; possible-submission audit; sender request token; local endpoint accepts while withholding response; complete HTTP response before receipt save; committed receipt; token cleared; engagement projection committed; job completed before cleanup | 10 |
| Gmail sequence email | Request token; endpoint accepts while withholding response; complete response before receipt; committed receipt; token cleared; provider operation accepted; logical intent executed | 7 |
| Microsoft sequence email | Same seven provider boundaries; accepted 202 response has no invented provider message ID | 7 |
| Hunter billable email lookup | Same seven provider boundaries; GET remains a billable possible side effect, with result projection fenced to the original lead | 7 |

Each case kills the requesting worker with SIGKILL, so exception/finally cleanup cannot run. Redis restores the unacknowledged message. The next isolated worker receives actual redelivered delivery metadata, executes the production job path, then invokes the production database recovery method. Recovery after a saved response makes no HTTP request; repeated cleanup leaves a simulated replacement owner's distinct hold untouched. The endpoint counts every request and performs no deduplication.

Zero requests are expected at the audit/token checkpoints before transport. One request is expected once transport reaches the endpoint, even if its response was never durably recorded. A manual interruption before any possible-submission marker may safely proceed once, because no submission marker was written. No possible submission is automatically reset to pending.

The loopback transport uses a strict method/host/path allowlist for the production URLs and strips authorization headers, cookies and query strings before local forwarding. Credentials are freshly generated test ciphertext. Production paid access, sender/proxy records, working hours, generation/source permission and content approval checks execute against the disposable database; readiness and authorization are not stubbed. The assigned proxy itself is bypassed by this test transport, so this does not establish proxy-only egress.

Harness: tests/outreach_physical_harness.py. Matrix: tests/test_outreach_physical_crashes.py. The harness refuses imports without its explicit test flag, requires test-prefixed database/queue names, and accepts only an exact numeric loopback endpoint. It uses a separate Celery application and never starts the application Celery runtime. Cleanup removes only the random test database and Redis key prefix; no shared flush occurs.

## Verification

- 649 distinct outreach backend tests pass: 613 in the final suite, 5 prior Redis/Celery publication/outbox drills, and 31 new physical crash cases. The final suite includes 17 real MongoDB concurrency/fault/index checks; 36 broker tests are intentionally skipped there and run separately with opt-in local services.
- All 31 physical cases pass; four representative cases also pass after protecting the endpoint counter with a thread lock and removing unused test arguments/imports.
- Changed production modules have 91% combined statement coverage: execution_permission 93%, manual_resolution 89%.
- Python compilation, medium/high Bandit and whitespace checks pass. Final Python review found no material critical/high issue; it independently ran 60 focused regressions.
- Frontend code is unchanged in this slice. The previous 79 frontend tests and production build remain the most recent frontend evidence; they were not rerun here.

To repeat the crash suite, supply disposable MongoDB on 127.0.0.1:27028 and Redis on 127.0.0.1:6389, then run:

```bash
OUTREACH_TEST_LOCAL_BROKER=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/test_outreach_physical_crashes.py -q
```

Test processes use a three-second Redis visibility timeout, explicit test-only feature flags and short operator grants. Lease timestamps are advanced only in the disposable database after killing the worker. These settings accelerate the drill; they are not production configuration changes. Owned services and workers are stopped after verification.

## Remaining release work

The isolated physical provider receipt/token crash gate is complete for the four listed paths. This is not live LinkedIn, IPRoyal, Gmail, Microsoft, Hunter, voice-vendor or OAuth-refresh verification. It also does not verify the production Celery pool/beat schedule, production timeout tuning, every private endpoint, kernel route isolation, replica-set transactions, workload identity, credential custody across process memory, or disaster recovery.

Next, establish strict ordering between revocation and dispatch across campaign, paid access, content approval and sender/proxy authorities. Current independent checks/CAS boundaries do not form one global transaction. Define the dispatch authorization boundary and revoke semantics, then test both race orders with real database writes before changing release claims. Integrate outreach collections into erasure/retention without deleting unresolved submission or provider-lease evidence. Offline voice preparation, custody/workload identity, proxy-only routing, restore fencing and purchased-seat/mailbox pilot evidence remain required before a separately authorized live release.

All three architecture documents are updated to v2.7.0 and synchronized to the Desktop copies. Pre-edit backup: /tmp/unravler-docs-before-v2-7. Earlier reports remain historical evidence.
