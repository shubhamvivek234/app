# Unravler.io — Suppression ordering and identity preservation

Date: 2026-10-03. Local implementation and isolated verification only. Live-action and conditional-launch flags retain disabled defaults. No commit, push, deployment, purchase, real execution grant or external provider request was performed.

## Result and ordering contract

Dispatch and participating suppression writers now write the same stable MongoDB workspace guard before reading their transaction snapshot. This closes the previous negative-lookup race: a newly inserted DNC/email/reply record, or a previously unrelated identity becoming a match, no longer escapes dispatch through a participating writer. A stop committed first forces authorization to see it or retry and deny before HTTP. Authorization committed first may complete; a later stop cannot cancel that request.

The pilot deliberately uses one guard per workspace rather than locks derived from individual recipient aliases. Its deterministic identity is initialized outside the transaction with majority read/write concern, then updated without upsert as the first transaction operation. Concurrent first use converges on the same majority-visible record. A missing guard during authorization denies rather than recreating it inside the snapshot. The guard revision has no TTL or periodic reset.

Both paths require snapshot transactions and majority commit. Database-only callbacks may retry; no provider HTTP runs inside them. Final transport still starts after authorization commit/session closure and synchronous expiry, freshness and schedule checks. Each operation has a ten-second overall bound and a five-second commit limit. Contention or unsupported transactions fail closed; production capacity and latency have not been measured. Workspace serialization is an explicit tradeoff for the small paid pilot, not a high-availability claim.

## Participating writers

| Writer | Committed group |
|---|---|
| DNC add API | Guard and normalized exclusion record; storage failure returns 503 without reporting success |
| Email suppression | Guard and normalized suppression upsert; nested mailbox calls reuse the same tenant/session |
| LinkedIn conversation persistence | Guard, thread/reply evidence, matching lead/task stops, applicable reply counter and outbox event |
| Mailbox inbound persistence | Guard, reference-attributed email suppression, matching lead/task stops, applicable reply counter, thread/event records and inbound deduplication marker |

Network fetch, OAuth and provider parsing remain outside these callbacks. Reply persistence errors abort the group and prevent successful complete-coverage publication; they are no longer swallowed as optional reporting errors. A scoped database wrapper requires the same workspace and session on callback reads/writes. Outbox deduplication inside a suppression transaction uses an idempotent upsert/read-back, preserving the original event instead of swallowing a duplicate-key error that aborts the transaction.

DNC records now retain immutable identity sets. Adding an email-only exclusion cannot remove a prior record that also excluded a LinkedIn URL. Repeated identical sets reuse a record; overlapping sets can remain separate entries, and an explicit deletion remains distinct from re-adding fewer aliases. Legacy exclusion records remain valid. Matching checks include both saved identifiers and current top-level fields, so a discovered email does not hide behind an older saved email. Sender-bound reply lookup checks both `linkedin.com` and `www.linkedin.com`, including later campaign enrollments.

Overlapping inbox updates preserve saved reply authority. Older, equal or undated fetched snapshots retain newer saved snippet/time/unread metadata and merge observed messages idempotently. Individual message timestamps use normalized parsed values; undated messages deduplicate by observed sender/content rather than ingestion time. Conversation timestamps normalize seconds, milliseconds and supported datetime forms before comparison/storage. Reply counters increment only on the first lead transition. None of these rules manufactures remote delivery or listening evidence.

## Boundaries and rollout

This is a **participating-writer protocol**, not MongoDB predicate locking. Manual database edits, older API/worker runtimes and future suppression writers that bypass the helper remain outside the guarantee. A relationship between unknown recipient identifiers cannot be inferred by serialization. Remote replies not yet observed and requests already authorized remain possible.

Before any separately approved rollout, drain **all older transport, inbox, mailbox and DNC-writer runtimes**, verify the actual deployment supports transactions/majority commit, verify required indexes including the unique workspace guard index, and confirm every current suppression producer uses this protocol. Check indexed outbox/inbound deduplication on the actual deployment. A single-node replica set supplies transaction features, not high availability. There is no new production bypass flag or standalone fallback.

Never expire, reset or delete guards while participating writers can run. Workspace deletion/retention must first stop and drain execution, account for unresolved submissions and provider-term assignments, and define minimal retained evidence before lifecycle cleanup. This deletion integration is the next implementation slice; ordinary document deletion is not sufficient.

## Verification

- **709 distinct outreach backend tests pass:** 669 in the final suite, five isolated Redis/Celery dispatch/outbox drills and 35 physical worker SIGKILL/redelivery cases. The 40 opt-in broker cases are skipped in the full suite and run separately.
- The full suite includes **73 real MongoDB cases:** 17 existing concurrency/fault/index checks, 23 dispatch-authority checks including an actual disposable standalone server, and 33 new suppression-ordering regressions.
- New cases cover six snapshot races for insert/identity-change variants, authorization-first ordering, rollback, tenant/session isolation, concurrent first guard creation, missing-guard denial, atomic LinkedIn/mailbox replies, indexed existing-event deduplication, transient transaction retry, saved/current aliases, DNC alias preservation, stale/equal/undated reply enrichment, later enrollment with either LinkedIn host, and numeric/missing timestamp idempotence. The standalone check now also denies email suppression and returns DNC API 503 without storing an exclusion.
- Production statement coverage is **92% for suppression**, **90% for dispatch_authority**, and **91% combined**. Python compilation, medium/high Bandit and whitespace checks pass. Independent Python review ran all 33 new real suppression cases and 67 focused regressions; all material findings were fixed and the final bounded release was approved with live actions disabled.
- Older minimal unit fakes isolate transaction orchestration through a test-only fixture. Atomic database tests opt out, and fresh crash-drill workers execute production authorization. No application fallback is introduced.
- The 40 separate broker/physical cases passed with the shared workspace guard in place. Their provider-facing paths use production guards/adapters over isolated loopback TCP. The final inbox timestamp changes are covered by the final full suite and independent 33-case run. No live vendor, assigned-proxy routing or production recovery behavior is inferred.
- Frontend code is unchanged. The previous 79 frontend tests and production build remain retained evidence and were not rerun in this slice. The unrelated broad backend account-erasure fixture issue is outside this outreach-only suite.

To repeat, initialize a disposable replica-set primary at `127.0.0.1:27028` and Redis at `127.0.0.1:6389`, then run:

```bash
OUTREACH_TEST_LOCAL_MONGO=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/test_outreach*.py -q
OUTREACH_TEST_LOCAL_BROKER=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin tests/test_outreach_execution_broker.py tests/test_outreach_physical_crashes.py -q
```

Tests use random databases/queue prefixes, generated ciphertext and disposable local grants. Temporary test-only flags do not change application defaults or production configuration. The local replica set used a ten-second transaction lifetime to accelerate killed-session abort; Redis used no persistence. Owned servers and workers are stopped after verification.

## Owning code and next work

Core: `outreach/core/suppression.py`, `dispatch_authority.py`, `lead_importer.py`, `email_finder.py`, `mailbox_sync.py`, `event_outbox.py`, `outreach/engine/inbox_sync.py`, `outreach/tasks/sequence_executor.py`, `outreach/api/leads.py`, and `db/indexes.py`. Evidence: `tests/test_outreach_suppression_ordering.py` and the extended `tests/test_outreach_dispatch_authority.py`, plus the existing physical/broker harnesses.

Next, implement outreach account/workspace erasure and retention with stop/drain ordering, secret/content cleanup, and minimal unresolved-submission/provider-lease/suppression evidence. Offline voice preparation, broader credential custody/workload identity, kernel proxy-only routing, restore fencing and purchased-seat/mailbox pilot evidence remain required before a separately authorized live release. Manual verified-invoice provisioning remains in place; automated billing/procurement is deferred.

All three architecture documents are updated to v2.9.0 and synchronized to the Desktop copies. Pre-edit backup: `/tmp/unravler-docs-before-v2-9`. The earlier [transactional dispatch authority](UNRAVLER_IO_ATOMIC_DISPATCH_AUTHORITY_RELEASE.md) report remains historical evidence for the narrower seventh-slice boundary.
