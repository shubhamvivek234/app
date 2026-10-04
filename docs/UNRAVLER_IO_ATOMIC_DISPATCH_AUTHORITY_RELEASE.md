# Unravler.io — Transactional dispatch authority

Date: 2026-10-02. Local implementation and isolated verification only. Live-action and conditional-launch flags retain disabled defaults. No commit, push, deployment, purchase, real execution grant or external provider request was performed.

## Result and ordering contract

Final physical dispatch now revalidates its applicable authorities in one MongoDB snapshot transaction with majority write concern. It writes each existing matching mutable row read by validation, the exact sender request token, content submission authorization where required, and the physical audit's dispatch_authorization together. Concurrent updates/deletions of those rows conflict or cause transaction retry. A stop committed before authorization wins; the lazy HTTP factory stays uncalled. A stop after authorization blocks later requests but cannot cancel the request already authorized.

The transaction includes applicable sender permission/generation, paid entitlement, seat, proxy lease/inventory, campaign/sequence, lead, existing matching inbox thread, job/target, provider resource, intent/attempt and content approval checks. Immutable sequence versions remain read-only; the mutable campaign/version binding is fenced. It does not transactionally combine subscription procurement, budgets, earlier possible-submission markers, later provider response storage or projection repair.

Authorization callbacks perform database work only. Driver retries never execute HTTP. Transport starts after commit and session closure. Before calling the factory, synchronous checks reject crossed permission, paid-term, proxy, custody, claim, approval and applicable inbox/mailbox freshness deadlines, and recheck the captured working schedule. An observed post-commit expiry is a proven non-call; existing conservative budget/refund and exact-owner cleanup rules apply.

Provider sequence validation preserves separate original job/lead ownership and physical request-parent/outbox ownership. It requires the original intent and attempt to remain in flight under the latter owner. Manual jobs and search page jobs supply transaction-aware validators using the scoped database; applicable connection and ordinary sender validation also use that scope. Authority references store collection names and hashed row identities, without credentials or content.

## Important boundary

This is ordering over **existing matching/read authority rows**, not a global predicate lock. A negative lookup does not conflict with insertion of a matching suppression/DNC/thread row, or with a previously nonmatching row changing identity into a match. Existing recipient threads are now read before testing their reply flags so a reply committed to an already matching thread conflicts even before a separate lead suppression update. More than 100 matching threads conservatively denies dispatch.

Unobserved remote replies and already-authorized requests remain possible. Complete suppression identity/negative-lookup coordination remains a release requirement. These limitations are not waived by passing the tests or by having transaction support.

## Deployment dependency and failure behavior

Production dispatch requires MongoDB sessions and multi-document transactions. There is no production legacy fallback or new bypass flag. An unsupported standalone server, transaction/session failure or authorization timeout denies dispatch before transport. The transaction has a 10-second overall authorization bound and a five-second commit limit; these are local implementation bounds, not measured production capacity guarantees.

Before any separately approved rollout, verify transaction capability on the actual deployment, drain older transport/connection/manual workers, verify the existing required indexes and grants, and confirm the current runtime uses these validators. A single-node replica set supplies transaction features, not high availability. Live provider flags remain disabled throughout this local slice.

## Verification

- **676 distinct outreach backend tests pass:** 636 in the final suite, five real Redis/Celery publication/outbox drills, and 35 physical worker SIGKILL/redelivery cases. The 40 opt-in broker cases are skipped in the final suite and run separately.
- The final suite includes 40 real MongoDB checks: 17 existing concurrency/fault/index cases and 23 new authority cases. New cases cover eight manual authority stops, eight provider sequence stops, a later stop, rollback, expiry, inbox coverage, working hours, an existing-thread reply race, and an actual disposable standalone server denying transport.
- The physical matrix uses production LinkedIn reaction, Gmail/Microsoft email and billable Hunter adapters over allowlisted loopback TCP. Each path adds an uncommitted transaction-token kill case to the prior 31 cases. After SIGKILL before commit, the token/dispatch authorization is absent; earlier possible-submission evidence still requires conservative recovery. After commit, the durable token checkpoint preserves the existing uncertainty/receipt rules. Saved responses repair without replay; replacement-owner tokens survive old cleanup.
- The new production dispatch_authority module has 90% statement coverage. Python compilation, medium/high Bandit and whitespace checks pass. Independent Python review ran all 23 new real authority cases, plus earlier 60 focused regressions, and found no remaining material blocker within this bounded scope.
- Older unit fakes isolate the new transaction method through a test-only fixture and retain their historical behavior. New atomic_dispatch-marked database tests opt out. Fresh crash-drill workers use production transactional authorization; no test-only authorization fallback exists in application code.
- Frontend code is unchanged. The prior 79 frontend tests and production build remain the latest frontend evidence and were not rerun here. No live vendor, assigned proxy routing, production pool/beat timing, workload identity or restore guarantee is inferred from loopback tests.

To repeat, start a disposable replica-set primary at 127.0.0.1:27028 and Redis at 127.0.0.1:6389. Initialize the test replica set before running:

```bash
OUTREACH_TEST_LOCAL_MONGO=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/test_outreach*.py -q
OUTREACH_TEST_LOCAL_BROKER=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/test_outreach_execution_broker.py tests/test_outreach_physical_crashes.py -q
```

Each drill uses random test-only databases/queue prefixes and generated ciphertext. The standalone case creates and stops its own loopback server. Physical drills use a short Redis visibility interval and disposable claim timestamps; our local replica set used a test-only ten-second transaction lifetime to accelerate abort of killed uncommitted sessions. None changes production configuration. Owned services/workers are stopped after verification.

## Owning code and next work

Core: outreach/core/dispatch_authority.py, request_guard.py and inbox_freshness.py. Validators: outreach/core/manual_actions.py, outreach/tasks/sequence_executor.py, sequence_dispatch.py and celery_workers/tasks/outreach.py. Evidence: tests/test_outreach_dispatch_authority.py, tests/outreach_physical_harness.py and tests/test_outreach_physical_crashes.py.

Next, close suppression identity/negative-lookup ordering gaps, then integrate outreach erasure and retention while preserving minimal unresolved-submission/provider-lease evidence. Offline voice preparation, broader credential custody/workload identity, kernel proxy-only routing, restore fencing and purchased-seat/mailbox pilot evidence remain required before a separately authorized live release.

All three architecture documents are updated to v2.8.0 and synchronized to the Desktop copies. Pre-edit backup: /tmp/unravler-docs-before-v2-8. Earlier reports remain historical evidence.
