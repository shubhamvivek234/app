# Unravler.io — Outreach erasure and retention

Date: 2026-10-03. Ninth implementation slice, verified locally. No commit, push, deployment, purchase, production execution grant or provider-side mutation was made. Live-action and conditional-launch flags retain disabled defaults. This is a bounded cleanup protocol, not a legal-compliance certification or a guarantee about backups and remote copies.

## Result

Account deletion now records a durable pending user, resolves all actually owned workspaces, stops outreach through the existing transactional workspace guard, and waits for an identified operator to drain every workspace writer before deleting outreach content. An active shared workspace selected in the user's profile does not make that user its owner. Other owners' business data is preserved; personal membership identifiers are removed or anonymized by the existing account worker.

The durable owned-workspace manifest survives partial cleanup. Legacy personal outreach records keyed by the user ID, or by user_id without a tenant, are adopted only into a proven personal scope. A conflicting real workspace owner denies that adoption. More than 1,000 owned workspaces or 10,000 records in an inspected collection requires a larger reviewed cleanup plan; results are never silently truncated. Unknown outreach collections stop completion until an explicit policy is added.

Even an empty workspace awaits drain: empty storage cannot establish that a previously admitted API request or worker holds no data. A fresh reviewed retry rechecks previously erased workspaces and revisits completed batch markers, so an older admitted writer cannot leave new records permanently skipped. Raw writers and old runtimes remain outside the admission protocol; the drain requirement includes them.

## Stop, review and purge

| Stage | Behavior and authority |
|---|---|
| Request | Persist user deletion_pending/due publication; block the Firebase UID by a majority-written digest; persist owned-workspace manifest |
| Workspace stop | Guard-first snapshot transaction and majority commit; permanent erasure_state, revoked entitlement, paused campaigns and latched sender permission |
| Secret cleanup | Scrub account/session, pending verification, mailbox/OAuth, Hunter, voice, integration/webhook and assigned inventory credentials; disable API keys and new deliveries |
| Drain | Operator stops and drains all API, worker, scheduler, integration and older/raw writers; acknowledgement is an assertion, not a detector |
| Inspect | Private CLI returns tenant counts, minimal hold descriptors and a digest; no recipient content or credentials |
| Finish | Fresh digest and drain evidence required; database-only batches of at most 200 rows share guard ordering; retention evidence and deletions commit together |
| Retry | Fresh inspection/drain revisits unfinished collections; transaction aborts do not discard originals or duplicate holds |
| Account completion | Existing generic collection cleanup runs only after owned outreach tenants are erased; external failures retain pending user and retry references |

No provider HTTP occurs inside stop/purge/retention transactions. Each control transaction has a 30-second bound and a five-second commit limit; multi-batch finish can take longer and is resumable. Snapshot transactions and majority commit are required; unsupported topology/transaction errors fail without claiming deletion. The persistent workspace guard has no TTL, reset or automatic reopening.

Customer outreach routes, public integration API-key paths, shared authorization, suppression persistence, paid access, execution grants and operator proxy import deny stopped tenants. Mailbox callback remains authenticated by its existing OAuth state/browser binding rather than an app JWT; a consumed state for a stopped tenant cannot enqueue a new credential job. Webhook delivery/fanout reads stop before sending, and copied delivery secrets/target URLs are scrubbed. These checks cannot erase credentials already held in process memory or cancel an HTTP request already authorized; those processes must be drained.

## Retained records

| Record | Retained material | Release rule |
|---|---|---|
| Unresolved submission | Source collection, record/row digests, bounded outcome label, mutation boolean and retention metadata | Explicit private fresh-digest retention review; removal never confirms sending, replays traffic or restores permission |
| Saved physical receipt | Bounded known outcome such as accepted, without provider body or recipient content | Explicit review; acceptance remains distinct from delivery |
| Unfinished connection cleanup | Minimal recorded completed/repair state | Explicit review; does not imply an unknown send |
| Financial reference | Receipt/entitlement digests and retention metadata | Explicit review according to an independently determined retention basis |
| Provider term | Minimal sanitized inventory/lease references, sticky tenant ownership, country/order/expiry and provider-hold descriptor | Fresh review requires both saved expiry and the current actually owned asset's expiry to have ended; missing ownership, renewal or unverified expiry denies release |
| Workspace closure | Stable suppression guard plus erased request/review digests | Persistent execution exclusion; no reopening or TTL |
| Deleted identity | account_erasure_tombstones: Firebase UID digest and request time | Persistent bootstrap exclusion; no plaintext UID, email or token, no TTL/reinstatement flow in this slice |
| Invoice reuse authority | account_invoice_guards: invoice digest and original workspace/seat/UTC-millisecond term binding digest | Permanent uniqueness authority, independent of releasable financial holds; deleting a receipt cannot fund a second tenant |

Known queued/non-dispatched records, accepted operations and fully cleaned completed connection jobs are not relabeled as uncertain. Ordinary leads, messages, rendered copy, DNC recipient records, approval/audit payloads and stored voice audio are deleted from the explicit outreach manifest. The remaining closed-workspace guard prevents that erased tenant from becoming executable after its recipient exclusions are removed. The hashes and minimal asset identifiers are pseudonymous evidence, not a claim of anonymization. The operator must establish lawful retention periods separately; this implementation invents none and schedules no automatic hold expiry.

Invoice claims reserve the digest before receipt/entitlement writes. Interrupted reservations can retry only their original binding and cannot themselves grant access. Existing receipts are backfilled before deletion. UTC BSON millisecond normalization is used before binding/write/comparison, including a real payment-to-erasure roundtrip regression. Multi-record payment activation remains a recoverable workflow, not newly transactional billing automation.

## Account worker and customer reporting

The scheduled pending-deletion publisher runs every 60 seconds, selects at most 100 due users and uses five-minute due timestamps for fair retries. Broker failure and worker interruption retain the pending user. All actually owned outreach tenants require operator drain review before the generic worker proceeds; this intentionally applies to empty tenants too.

Storage/Firebase/payment failures do not remove the pending user or its retry references and do not return completed. Confirmed absent Firebase users and storage objects allow idempotent retries. Stripe/Razorpay cancellation first reads the exact subscription ID and accepts an already-canceled status; a lost cancellation acknowledgement can therefore be recovered from the next read. Wrong identities, missing configuration, arbitrary not-found errors and unverified responses stay pending. [Stripe cancellation contract](https://docs.stripe.com/api/subscriptions/cancel) and the installed Razorpay subscription fetch/cancel adapter informed these checks. Tests use stand-ins; there was no live payment cancellation verification. The installed local Razorpay package cannot import because pkg_resources is missing, so production SDK compatibility remains an explicit prerequisite.

Settings and privacy/deletion copy describe pending cleanup, shared-data preservation and retained records. The public confirmation lookup returns not_found for unknown codes and unknown for incomplete records. The frontend reports unavailable on a failed lookup, renders server-recorded details, and cannot invent a completion or verification timestamp. This public tool still covers existing platform confirmation records; the account-deletion API does not create a new public confirmation code/status workflow in this slice. Meta's platform-specific deletion callback remains separate and has not been audited here.

## Private operator procedure

Run only on a trusted backend with its existing DB_NAME/MONGODB_URI configuration. Do not put credentials or recipient content in evidence arguments. The CLI commands inspect or change only database control/retention records; they never call a provider.

1. Receive the deletion request and check pending user publication/owned tenant manifests. Resolve partial-stop failures before treating outreach as stopped.
2. Stop and drain **all workspace writers**, including API/integration processes, schedulers, old workers, pending transport and inbox/connection runtimes. A missing record is not evidence of a drained writer.
3. Inspect each owned workspace with `python -m outreach.ops.pilot inspect-erasure --workspace WORKSPACE_ID`.
4. Review counts/holds and use the returned digest with `finish-erasure`, supplying `--operator`, `--evidence`, `--review-digest` and the exact `--workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS` acknowledgement. Keep processes drained until the request reports erased.
5. After interruption, obtain a new inspection digest and renewed drain evidence before retrying. Unknown collections/capacity failures require explicit policy/planning; do not bypass them.
6. Confirm the durable pending user retry can complete the existing generic storage/account/auth/payment cleanup. Pending external cleanup is not completed erasure.
7. Review a held record using `inspect-erasure-hold --workspace WORKSPACE_ID --hold HOLD_ID`; separately use `release-erasure-hold` with identified operator, evidence and current digest only when its retention basis permits. Provider review also checks current tenant ownership and expiry. Invoice/identity/workspace exclusion authorities remain persistent.

## Verification

- **771 distinct outreach backend tests pass:** 731 in the final suite plus five Redis/Celery dispatch/outbox drills and 35 physical request SIGKILL/redelivery cases. The 40 opt-in broker cases run separately.
- **20 account-deletion/auth companion tests pass** in the same 751-test main run; the repaired legacy fixture now includes query_string and explicit authority mocks. Combined backend verification is 791 distinct checks, not a full unrelated-product backend run.
- **62 new disposable MongoDB erasure regressions** cover ownership/shared data, legacy personal scopes, stop-before-HTTP ordering, rollback, empty/late writers, repeat/partial-batch retry, unknown collections, capacity, sanitized inspection, retention/current asset renewal/ownership, OAuth/API keys/webhooks, deleted-token/profile races, invoice reuse/concurrency/BSON roundtrip, broker publication failure and external cleanup retry/reporting. The broader suite also runs the prior 73 real Mongo checks including actual index setup and standalone dispatch/suppression denial. Extended focused checks also verify standalone erasure denial, unique erasure requests, persistent no-TTL control indexes and the pending-user due index.
- Production erasure statement coverage is **95%**. Independent Python review passed 74 focused erasure/account/payment tests and found no remaining high/critical issue in this bounded live-disabled release. Python compilation, medium/high Bandit and whitespace checks pass.
- **85 frontend tests pass:** the prior 79 outreach tests plus six new deletion-status regressions. Production build passes with existing Browserslist/Tailwind/PostHog source-map/bundle warnings. Final missing/invalid-date behavior and guide-label adjustments have focused verification.
- Isolated broker/provider drills use real Redis/Celery, disposable Mongo and production adapters over loopback HTTP. Final payment-adapter tests stub all calls. An early red test accidentally reached Stripe's legacy delete endpoint with a dummy test-only key and fabricated subscription ID; no production credentials were used. That legacy test route is now explicitly blocked. This is disclosed rather than counted as live verification.
- Disposable replica-set primary: 127.0.0.1:27028; Redis: 127.0.0.1:6389 with no persistence. Generated keys/random test databases/queue prefixes and temporary test flags do not modify production defaults. Owned services are stopped after verification.

Repeat the main check with OUTREACH_TEST_LOCAL_MONGO=1 and the existing pytest command, including tests/test_account_erasure.py and tests/test_auth_security.py; run the opt-in broker/physical files separately with OUTREACH_TEST_LOCAL_BROKER=1. Never point these fixture/drill suites at production.

## Scope, next work and documents

This slice deletes the explicit outreach database manifest and integrates the existing generic account worker. It does not certify whole-product collection coverage, external copies or token revocation across every social platform. Backup erasure/restore fencing, legal retention decisions, deleted-identity reinstatement, kernel egress isolation, workload identity/KMS custody, automatic writer-drain detection and live purchased-IP/mailbox/voice checks remain outstanding. Remote scheduled work and already-authorized calls require operational coordination. Keep live flags disabled.

Next implement offline voice preparation and operational credential/workload identity, proxy-only egress and restore-fencing evidence; then perform separately authorized purchased IPRoyal seat and mailbox pilot verification. Manual verified-invoice provisioning remains in place; automated subscription/proxy procurement is deferred.

All three specifications are v2.10.0, synchronized to their Desktop copies. Pre-edit backup: /tmp/unravler-docs-before-v2-10. Earlier [suppression ordering](UNRAVLER_IO_SUPPRESSION_ORDERING_RELEASE.md) remains historical evidence. Core ownership: outreach/core/erasure.py, suppression.py, paid_access.py, managed_proxy.py, dispatch_authority.py, execution_permission.py, event_outbox.py, webhook_delivery.py; API/worker integration: api/deps.py, api/routes/user.py, celery_workers/tasks/gdpr.py, outreach/api/router.py, integrations.py, mailboxes.py, outreach/core/mailbox_connection.py, outreach/ops/pilot.py and db/indexes.py.
