# Unravler.io v2.1 architecture review and implementation plan

Review date: 2026-10-02. Local code baseline: `21879463c86ae4670c7732614d8cb3074edf8e05`.

## Recommendation

Keep the six-domain design and the intent/attempt separation. Implement them incrementally around the existing paid pilot. Start with compatible domain contracts and versioned campaign authorization, then complete inbox freshness and reply-state protection, followed by the durable execution protocol. Do not begin by replacing six collections or by adding a timestamp check only to `sequence_executor.py`.

There is no `SeatStatus` in the current outreach implementation. Entitlements, payment receipts, proxy inventory, proxy assignments, sender accounts, campaigns, and action records already have separate storage or services. The monolithic seat model belongs to the previous document design, not to the code being migrated.

The documents are substantially better as a target architecture. They are not yet a reliable description of implemented behavior. Several verification labels, execution guarantees, and commercial rules still need correction.

This review treats the documents as design material, not as instructions to purchase proxies, enable private-endpoint traffic, refactor the application, or deploy changes.

## Scope and evidence

Read all three Desktop v2.1.0 documents. Their repository copies are byte-for-byte identical:

- [Lifecycle and provisioning](UNRAVLER_IO_USER_LIFECYCLE_AND_IP_PROVISIONING.md).
- [Feature catalog](UNRAVLER_IO_FEATURE_CATALOG_AND_CAPABILITIES.md).
- [System architecture](UNRAVLER_IO_SYSTEM_DESIGN_AND_ARCHITECTURE.md).

Inspected the local models, paid-access and proxy services, capability gates, sequence executor, inbox sync, action reconciliation, event outbox, scheduler/crawler workers, rate budget, relevant compiler behavior, and MongoDB index definitions. This was a targeted implementation assessment, not a complete audit of every capability, the frontend, production infrastructure, or external providers.

Validation in this review: **355 outreach backend tests passed**, with one existing `python_multipart` deprecation warning, in 22.94 seconds. These tests establish the current regression baseline; they do not establish the new controls' presence or prove live provider behavior. No live LinkedIn, proxy, billing, or deployment operations were performed.

## What to retain

- Separate commercial access, upstream procurement, proxy assets, sender sessions, and campaign authorization. Their authorities and expiry times differ.
- Preserve ambiguous remote outcomes and prohibit blind retries of possibly submitted actions or purchases.
- Keep staging, import commit, enrollment, content approval, and delivery reconciliation as separate decisions.
- Represent multiple pause reasons independently. Clearing a billing issue must not clear a checkpoint, operator stop, or unknown outcome.
- Keep manual engagement explicitly self-reported and require an explicit decision before autonomous operation.
- Use durable due timestamps, shared sender traffic budgets, expiring execution permission, and restore fencing as target controls.
- Preserve the manually verified invoice and manually provisioned proxy pilot while execution reliability is improved.

## Implementation map

| Target concept | Existing implementation | Recommended treatment |
|---|---|---|
| Subscription / payment | `outreach_payment_receipts` and operator-verified invoice service | Define a provider-neutral payment contract. Defer automated Stripe subscription processing. |
| Entitlement | `outreach_entitlements`, `entitlement_is_active`, expiry cleanup | Add a typed contract around existing records; retain paid-term and seat checks. |
| ProviderOrder | Imported inventory can store a provider order reference; no automated procurement workflow in the inspected pilot path | Keep procurement operator-driven; implement an order workflow when automated procurement is needed. |
| ProxyAsset | `outreach_proxy_inventory` | Preserve asset identity, workspace ownership, country, and provider expiry. |
| Proxy assignment | `outreach_proxy_leases` and sender slots | Retain as an explicit relationship; six business domains do not mean exactly six collections. |
| SenderConnection | `outreach_accounts` and asynchronous connection jobs | Preserve existing IDs and statuses through adapters; add credential/session generation. |
| CampaignAuthorization | Campaign status and warm-up authorization fields | Introduce revisions, pause-reason sets, and one authoritative eligibility service. |
| ActionIntent / ActionAttempt | `outreach_tasks` operation claims plus a separate email operation ledger | Migrate conservatively; retain deduplication and uncertainty evidence. |
| Integration event outbox | `outreach_event_outbox` and webhook delivery records | Reuse appropriate patterns, but distinguish it from the proposed execution outbox. |
| Inbox freshness | Inbox synchronization and reply updates exist | Add a durable, scoped coverage marker and enforce it at dispatch. |

Evidence: `outreach/core/paid_access.py:32–114`, `outreach/core/managed_proxy.py:77–137`, `outreach/models.py:96–182`, `outreach/tasks/sequence_executor.py:38–75`, `outreach/core/event_outbox.py:21–79`, `db/indexes.py:145–168`.

## Remaining changes to the specifications

### 1. Correct implemented-versus-target labels before using the docs as acceptance criteria

The status legend is useful, but each implemented claim needs a code location, test, commit, and separate live-verification status. Split mixed sections into implemented behavior and target behavior.

Specific discrepancies:

- D1 Step 5 / D3 Subsystem F label KMS envelope encryption as built. The inspected secret path delegates to **Fernet**, not KMS/AES-GCM (`outreach/core/crypto.py:5–21`). Classify the new custody design as planned until implemented and tested.
- D2 Feature 5 labels cryptographically bound content approval as implemented. The inspected action-review endpoint records a **human assertion about an uncertain outcome**, not approval of message content (`outreach/api/action_reconciliation.py:35–38,173–177`). The launch gate checks uncertain action records (`outreach/api/campaigns.py:1020–1032`); that is not a per-message approval hash check.
- D1 scheduler section / D3 Subsystem B show an `outreach_intents` poller and per-sender serialized JIT publishing. The current scheduler scans due **leads**, claims them with `execution_claimed_at`, and calls the executor within the batch (`celery_workers/tasks/outreach.py:514–640`). Its default scan interval is 30 seconds, not 60.
- D2 Feature 9 / D3 Subsystem D describe a 15–30-minute business-hours inbox schedule and dedicated sync worker. The inspected registration schedules inbox sync every **300 seconds on the `outreach` queue** (`celery_workers/tasks/outreach.py:277–328`). Queue registration does not demonstrate a separate deployed worker.
- D2 lists Free InMail as a capability, but the supported LinkedIn dispatch set does not contain it (`outreach/core/sequence_capabilities.py:12–19`). Mark it planned/unsupported in the execution matrix.
- D2 says the compiler enforces a maximum of 15 nodes. The inspected compiler validates node shape, types, delays, roots, edges, and cycles; it does not enforce that limit (`outreach/core/dag_compiler.py:73–135`). Verify other validation layers before describing a universal server-side limit.
- D1 Step 2 claims live IPRoyal product-stock validation and checkout blocking. The inspected pilot entitlement path checks **local country-matched inventory covering the paid term**, and supports operator-verified payment (`outreach/core/paid_access.py:48–75`). Do not describe a product-query checkout path as verified on that evidence.

Treat exact RAM figures, per-proxy prices, provider product/plan IDs, and provider schema assumptions as measured results or dated account-specific inputs. This review did not verify those numbers against a current provider invoice or live account.

### 2. Specify a migration, not just replacement schemas

D1 entitlement fields and D3 canonical examples use ObjectId relationships. The application uses public UUID-string IDs (`outreach/models.py:12–13`) alongside some purpose-specific `_id` keys. D3 collection names also differ from existing ones.

Preserve external IDs and collection identities initially. Define mappings for `seats` versus `seat_allowance`, `active` versus `connected`, and existing payment sources. Adding model classes alone does not change the authority of any worker or API.

Choose one authoritative campaign authorization record. An embedded contract can be appropriate for the pilot; a separate collection is justified only if its consistency rules are explicit. Avoid independently writable campaign status and authorization status.

Keep proxy asset status separate from assignment occupancy. Current inventory can remain `available` while a separate lease establishes ownership. A migration that interprets `available` as unassigned could reuse an occupied IP.

Add enrollment identity and immutable sequence versions before using them in action deduplication. A changed key must never turn an old possibly sent action into a fresh send.

### 3. Fix the access-mode boundary

D1 Mode B includes search imports and says there is zero platform automation risk. D2 gates one-click search crawling with the live-action flag. D3 ADR-002 says the Search Importer operates independently of live automation. These are different behaviors.

Define separate rows for customer-supplied CSV/pasted leads, staged review of stored data, and authenticated LinkedIn/Sales Navigator crawling. The crawler performs automated private-endpoint reads and needs the corresponding authorization and traffic controls. LinkedIn's published policy explicitly includes crawlers and automated access; user initiation does not establish platform permission. [LinkedIn policy](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibited-software-and-extensions).

Keep the wider Unravler social scheduler and Smart Bio context separate from the outreach product's availability matrix. Official publishing permission must be assessed for the particular integration and scopes.

### 4. Preserve paid-period semantics and independent provider expiry

D1's billing state machine grants entitlement on checkout completion and advances `paid_through` by 30 days for recurring payment. Specify validated paid invoice coverage instead. Do not add 30 days to an existing clock on each event; duplicate or out-of-order events can otherwise create incorrect access. Stripe explicitly documents both behaviors. [Stripe webhook guidance](https://docs.stripe.com/webhooks).

For the current pilot, keep the existing verified external invoice path. Future Stripe support should reconcile provider objects, invoice identity, payment status, paid coverage, cancellation effective date, and administrative revocation. Removing a billing pause reason must not itself resume campaigns or clear other reasons.

D1/D3's fixed 48-hour dispatch cutoff would make a 30-day proxy term unusable for its last two days. Specify renewal warnings and a justified dispatch-duration safety margin separately from paid access. If a 48-hour reserve is an intentional product rule, obtain coverage for it and explain the resulting commercial behavior before implementing it.

D1 also alternates between retaining a disconnected sender's IP until billing expiry and until provider expiry. Use explicit assignment-retention rules keyed to provider expiry and sticky ownership. Ending app access does not erase remaining provider charges or justify cross-customer reuse.

### 5. Make the inbox freshness contract complete

A sync timestamp younger than 30 minutes bounds known staleness; it does **not** prevent a follow-up when a new reply arrives after the last poll. For example, a reply at 10:20 is still unknown to a sender last synced at 10:00 when a follow-up runs at 10:25.

Define a durable marker scoped to workspace, sender, channel, and credential generation, with sync start/completion times, cursor or coverage watermark, parser version, and completeness status. Set freshness only after the covered inbound data and suppression updates are durably committed. A reconnect, partial page failure, unrecognized schema, missing timestamp, or future timestamp must not create freshness.

The current inbox fetch loop stops after at most 500 conversations (`outreach/engine/inbox_sync.py:75–82`). Reaching a cap must not imply complete account coverage. Define whether the guard requires complete account coverage or a fresh synchronization of the relevant conversation, and implement that choice explicitly.

Deduplicate priority-sync requests per sender, reserve capacity for them, and persist deferred work. Define how repeated sync failure becomes visible without causing retry storms.

Immediately before a mutation, reread reply/DNC state and applicable authorization. Protect post-action state advancement with conditional updates so it cannot overwrite a concurrently recorded `REPLIED` state. Current execution reads the lead at the start, but dispatch occurs later and updates at lines 512, 527, and 628 match only the lead ID (`outreach/tasks/sequence_executor.py`).

State the guarantee precisely: a durably recorded suppression prevents subsequent authorized dispatch; recently completed polling reduces unobserved-reply exposure. Polling cannot promise elimination of every remote reply race. Define explicit behavior for reply-conditioned branches rather than treating every replied lead identically.

Apply channel-appropriate policy. Inbox sync itself must be able to run when freshness is missing. Search reads must not depend on LinkedIn inbox freshness, and email follow-ups need mailbox freshness rather than a LinkedIn timestamp.

### 6. Finish the intent/attempt recovery protocol

D3's happy-path sequence diagram lacks recovery at several boundaries: database claim before broker publish, duplicate delivery, queue delay beyond the claim TTL, crash before dispatch, crash during dispatch, and remote success followed by a database failure.

Specify:

1. A durable logical identity including workspace, enrollment, immutable sequence version, node, and action kind. Bind sender assignment and approved content through authorization revisions; changing them must not silently authorize a duplicate action.
2. Publication/claim ownership distinct from a network attempt. A broker retry is not automatically a new provider attempt.
3. Compare-and-set transitions using an owner token and revision. Only the current owner can enter possible submission, finalize the result, or release a claim.
4. An execution lease and explicit expiry/heartbeat rules. A 60-second claim must not be reclaimed as safe-to-send merely because a queue or provider call took longer.
5. A durable boundary indicating that submission may have started. If that boundary was crossed and the result is unknown, preserve the attempt and stop; do not reclaim it into a sendable state.
6. Atomic or recoverably idempotent updates across intent, attempt, lead advancement, and emitted domain events. Verify MongoDB transaction support before relying on multi-document transactions.
7. Distinct outcome/evidence values: `not_submitted`, `provider_accepted`, `observed_sent`, `observed_delivered` where available, `unknown_outcome`, and `human_assertion`. HTTP 200 plus a URN must not automatically mean delivered.
8. Reconciliation that can remain unresolved, record human attestation separately, or stop a lead. It must not manufacture delivery proof or implicitly resume a campaign.

The existing task ledger already prevents blind automatic re-sending through a unique `(workspace_id, id)` index and conservative uncertainty handling (`db/indexes.py:167`; `outreach/tasks/sequence_executor.py:38–75,318–363`). Preserve this protection during migration.

The integration event outbox accepts an optional database session, but the inspected inbox call does not couple reply-state updates and event insertion in a transaction. Distinguish an atomic update to one lead from an atomic transition covering every downstream action and event.

### 7. Make traffic ownership and scheduling executable

The proposed shared budget is valuable. Count actual upstream requests, including pagination, profile resolution, status checks, media operations, and reconciliation reads. One inbox sync can issue 20 page requests before other reads; a single UI action is not necessarily one request.

Use atomic sender-wide reservations and a shared durable authority. Current `RateBudget` reads counters before incrementing them and falls back to process-local memory when Redis operations fail (`outreach/core/rate_budget.py:141–230`). That is not a cross-worker fail-closed budget. The sequence executor also uses a separate daily limiter. Sync and safety reads require reserved capacity so crawls cannot starve them.

Add sender-level coordination across crawling, synchronization, and mutations. The crawler's unique active-job constraint is not a universal sender lock. Lease expiry does not cancel an already issued remote request; recovery must preserve uncertainty for possible submission.

D3 says countdowns above five minutes are banned, but the crawler passes uncapped `retry_after` to `apply_async` (`celery_workers/tasks/outreach.py:898–904`). Store long crawl deferrals durably as well. Five minutes is an application policy, not a universal Redis visibility timeout: Celery documents redelivery when countdown exceeds the configured `visibility_timeout`. [Celery scheduling guidance](https://docs.celeryq.dev/en/stable/userguide/calling.html#eta-and-countdown).

### 8. Reconcile execution-lease health rules

D1 specifies a 5% challenge tripwire over 14 days, while D1/D3's positive lease uses 1% without a matching window. In a pilot of 10–20 senders, one challenged sender represents 5–10%; percentages alone are misleading at that scale.

Specify the denominator, window, minimum sample, sender/cohort/cluster scope, latch behavior, and reset authority. Separate an operator halt and hard restriction signal from statistical monitoring. A successful generic proxy probe must not authorize all senders whose individual proxies are unhealthy.

Workers must explicitly check `expires_at`; TTL deletion is cleanup, not permission. Define freshness of the monitor inputs and fail closed on missing or unreadable authorization. Say that expired permission blocks new dispatch, not that it cancels every in-flight network request within 60 seconds.

### 9. Complete the custody, egress, and recovery topology

A network with no default internet route needs explicit permitted paths to MongoDB, Redis, DNS, the assigned proxy endpoint, and any required control services. Separate the LinkedIn transport worker from generic webhook or model-provider egress. Include IPv6, redirected requests, proxy failure, and host firewall behavior in the tested design.

IMDSv2 hop limit 2 helps metadata responses reach containers. It does not grant separate IAM roles to containers on a shared EC2 instance or provide a route to KMS. Specify workload identity, metadata restrictions, KMS permissions, key versions, and the credential migration procedure. [AWS metadata options](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-options.html).

Define canonical, unambiguous encoding for encryption context and content-approval bindings. Include tenant, sender, recipient, enrollment, sequence version, policy version, and relevant content identity. Plain concatenation without field framing is an incomplete contract.

D3's topology advertises PITR while its backup section specifies daily snapshots. Choose a recovery objective and backup method that actually meets it. A single-node replica set enables certain database features but is not high availability.

A per-record `restored_from_backup` field alone cannot fence old broker messages or an older backup of an authorization. Restore into a stopped environment, establish a new restore/execution epoch, invalidate legacy queue authorization, reconcile possibly submitted actions, and require explicit reauthorization. Test this by restoring an actual backup into an isolated environment.

## Recommended delivery sequence

### Step 0 — Close the contract and evidence gaps

Use the implementation map above as the starting point. Correct the three docs' status labels, billing-period semantics, access modes, freshness guarantee, and recovery transitions. Add evidence entries for capabilities outside this targeted assessment rather than assuming their labels are accurate.

Done when each requirement has a target/implemented classification, an owning code path, an acceptance check, and explicit migration semantics. The backend regression baseline for this step has already been run.

### Step 1 — Add compatible domain contracts and authorization revisions

Introduce typed contracts around existing entitlement, inventory, assignment, and sender records. Add campaign authorization revision, independent pause reasons, credential generation, and immutable enrollment/sequence identity. Implement one eligibility decision service that returns an actionable reason and is used by APIs and workers.

Start with `outreach/models.py`, the paid-access/proxy services, campaign mutations, and the worker eligibility boundary. Keep current public IDs, invoice processing, proxy leases, and action deduplication. Do not create an operational dependency on future Stripe or reseller-order services.

Done when old records remain readable, legacy API behavior is preserved, revocation makes queued revisions stale, one cleared reason cannot resume an otherwise blocked campaign, and workspace isolation tests pass. Missing migration metadata must not silently enable execution.

### Step 2 — Complete inbox freshness and protect reply state

Implement the freshness producer in inbox sync and the consumer at dispatch together. Add coverage/generation markers, deduplicated priority sync, durable defer reasons, final reply/DNC checks, and conditional post-dispatch lead updates. Apply equivalent mailbox rules to email follow-ups. Ensure inbox sync can acquire capacity without requiring an already-fresh inbox.

Done when missing/stale/partial freshness defers sends, reconnect invalidates prior freshness, a recorded reply between the initial scan and dispatch suppresses the action, and a reply during an already submitted request cannot be overwritten by executor completion. Explicitly test reply-conditioned branches.

This is the highest-value immediate correctness change after the small identity/authorization foundation. A timestamp comparison added only to `sequence_executor.py` is insufficient.

### Step 3 — Implement durable intents, attempts, and recovery for one action path

Begin with a rendered LinkedIn follow-up message through a fake transport while live actions remain disabled. Persist intent before publication, atomically claim worker ownership, establish sender execution ownership, record possible submission before the call, and finalize with preserved evidence. Integrate the Step 2 guard.

Test broker publication failure, duplicate delivery, stale claim tokens, queue delays, worker crashes at each boundary, provider timeout, and database failure after remote acceptance. Expand the protocol to invites, voice, email, manual inbox replies, and other mutations after the first path is proven; no live path should bypass the common dispatch boundary.

Done when duplicate tasks cannot create multiple physical submissions, a possibly submitted action never becomes automatically sendable after lease expiry, unknown outcomes remain visible, and lead progression is recoverable without re-sending. Verify transaction prerequisites where required.

### Step 4 — Unify budgets, execution permission, and content governance

Move all sender private-endpoint reads and writes under a shared atomic request envelope with reserved sync capacity. Remove long crawler countdowns. Introduce expiring positive execution permission with reconciled health thresholds and operator latching. Add version-bound content approval if approved-message mode is a product requirement; preserve its distinction from outcome review.

Done when multiple workers cannot overspend the shared envelope, unavailable budget/permission storage denies remote traffic, crawlers cannot starve required sync, old authorization cannot dispatch after revocation, and no unrelated pause reason is removed by recovery.

### Step 5 — Verify credential custody, egress, recovery, and the paid pilot

Implement the custody and network design that the documents retain as requirements, then validate real proxy identity/expiry, sender verification, and the local mailbox pilot. Exercise an isolated restore and prove old pending work cannot execute. Measure resource use and request counts instead of relying on architectural estimates.

Done when the chosen credential controls and proxy-only LinkedIn route have concrete evidence, restoration is fenced, purchased inventory and paid terms are reconciled, and pilot instrumentation reports observed outcomes accurately. Enabling live actions remains a separate explicit release decision; this review does not enable them.

### Later — Automate procurement and subscriptions

Build provider-order reconciliation, renewal, and Stripe lifecycle handling when expanding beyond manual provisioning. Keep the six-domain contracts ready for those integrations, but do not delay inbox and execution correctness to build unused commercial automation.

## Migration and rollout rules

- Use additive, versioned schemas first. Backfill with dry-run counts, invalid-record reports, and explicit ownership.
- Keep existing successful and uncertain action records as authoritative evidence. Maintain a deterministic mapping from legacy operation IDs to new intent identities.
- Pause and drain affected workers for any authority-changing cutover, or deploy an explicit compatibility protocol. Old and new dispatchers must never execute the same enrollment independently.
- Rollback must not restore an older permissive authorization or erase the unknown-outcome ledger. A failed cutover stops dispatch until reconciliation.
- Do not combine UI cleanup, payment-provider migration, proxy procurement, encryption changes, and execution cutover into one release.
- Re-run focused meaningful tests for each step and the outreach baseline at integration boundaries. Add production-like MongoDB/broker fault tests for the new durability guarantees; existing mocked tests alone are insufficient.

## First implementation scope

The next code change should be **compatible authorization and identity contracts**, with a bounded follow-up change for **complete inbox freshness and reply-state protection**. The full six-domain replacement is unnecessary for this pilot, and the durable execution outbox requires more than two model classes. Both proposed workstreams remain on the roadmap, with these dependencies and acceptance criteria made explicit.
