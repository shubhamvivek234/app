# Unravler.io — Outreach gap and implementation master plan

Version: 2.5.0 | Updated: 2026-10-21 IST | Baseline: committed v2.95 plus reviewed local sender fixes

This is the consolidated register of known outreach work. It replaces the older 7-video feature matrix and its unverified 12-day estimate. Track each bounded implementation against its acceptance evidence; a feature being visible, implemented in source or passing fixtures does not establish production activation or successful provider execution.

## Evidence and status rules

The [v2.95 flow audit](UNRAVLER_IO_PROSP_FLOW_AUDIT_AND_REPAIRS_RELEASE.md) records the authenticated Prosp inspection and its limits. The user's Ulaa workspace showed five import sources, templates and sender forms; imports required a connected sender and draft creation required a trial. Paid editor behavior, successful collection and physical launch were not exercised. REA analyzed four shipped assets from observed URLs with partial semantic coverage; authenticated debugger bytes were not reconciled. Prosp's private databases, crawler separation, queues, pricing economics, account-safety claims and conversion performance are not established facts.

The older video index is historical research material. This reconciliation did not retrieve or certify those transcripts again. Previously asserted internal architecture, blanket action counts, live conversion claims and arbitrary daily action limits must not be used as implementation authority.

Status meanings:
- **Committed**: reviewed source saved in local Git; does not imply pushed or deployed.
- **Local implementation**: source and targeted regressions exist; final verification and exact limits are in the fixes log.
- **Partial**: a narrower usable capability exists, with specified remaining work.
- **Open**: no completed implementation/evidence is claimed.
- **Decision required**: a supported provider, product or operational choice must precede dependent work.
- **Operational**: requires a separate authorized cutover or controlled live verification.

Current reports are [the continuation fixes log](UNRAVLER_IO_REMAINING_FIXES_LOG.md), [the product roadmap](MASTER_PRODUCT_ROADMAP.md) and the three architecture specifications. Older release reports retain their dated scope.

## Completed baseline and corrected earlier claims

| Area | Current verified scope | Limits |
| --- | --- | --- |
| v2.95 intake repairs — committed as 6fa7ca0 | CSV/profile/staged-search validation parity, edited names/location, exclusion rechecks and current-plus-saved identity persistence. | No historical lost-identity backfill or working search/post/network/finder adapter. |
| v2.95 sequence/launch repairs — committed | Saved working hours and unavailable sender selections retained; draft CAS advances authorization; broken sender/node continuity and terminal-only launch hold. | Same-ID semantic changes and reviewed progress migration remain open. |
| v2.95 sender repairs — committed | Disconnect/install contention, custody scrubbing, reconnect hold policy and original-job retries in the open modal. | This release itself did not provide recovery after reload. |
| Current sender identity reservation — local implementation | Existing account/fence reserves an exact observed URN within a workspace, atomically with preparation; install rechecks identity and native record. Duplicate/current-job/malformed/bounded-capacity cases hold. | See S01 for limits; no new production unique index or legacy duplicate migration. |
| Current verification recovery — local implementation | Bounded server discovery and explicit original-job checks survive reload when records remain; current context and completed-account binding are checked. Unknown scoped POST cannot be resubmitted in the same open dialog. | See S02 for missing/expired records, stopped-job and session-context limits. |
| Supported sequence conditions | Current capability catalog implements connected, usable-email and typed data-column paths under their separate flags/authorities. | The old claim that all other conditions silently fall through is stale; unsupported choices must remain unavailable. |
| Sequence preview and compiler | Stored graph validation, typed observations, sample rendering, branch/delay/provenance checks and governed template revisions already exist. | Runtime AI generation and complete live-provider parity are separate. |
| Voice preparation/Studio | Consent-bound durable Studio, voice preparation, encrypted artifacts and separate provider contracts exist in source. | “Static audio only” is an incomplete description. Canvas mic/upload controls, activation, older-data custody and live vendor fidelity still need their own completion evidence. |
| Inbox snippets and tags | Existing inbox APIs and composer/drawer implement saved snippets and tags. | They are not wholly missing. Any usability change needs a specific new gap rather than reimplementing those features. |

## 0. Shared identity correction and remaining identity review

| ID | Status | Remaining change | Acceptance and edge cases |
| --- | --- | --- | --- |
| A01 | Bounded correction implemented locally; broader identity census remains | Correct shared authentication email fallback and duplicate-key email recovery in `api/deps.py`. | Reject an account already linked to a different stored Firebase UID before any profile update/return; cover mismatched UID/email and races, no-profile-write, valid same-UID and deliberate legacy-link policy. Current import/sender digests bind permission-resolved stored identity, not independent raw-cookie certification. Review broader authentication/legacy linking before claiming complete account-switch protection. |

## 1. Sender reliability and recovery

| ID | Status | Remaining change | Acceptance and edge cases |
| --- | --- | --- | --- |
| S01 | Partial — local reservation implemented | Review existing duplicates, cut over all participating writers and decide any future cross-workspace identity policy. | Concurrent jobs, sole-owner reconnect, stopped/deleted/uninstalled reservations, same public ID on two native rows, changed current job, native binding, rollback, erasure, standalone denial and unknown acknowledgement. Current policy uses exact opaque URNs within one workspace; no guessed alias equivalence, global uniqueness or legacy repair. Unrelated missing/null identities are not inferred as aliases. More than 100 sender rows holds; a new row at capacity is denied. |
| S02 | Partial — local server recovery implemented | Durable handling of absent/expired original records, ambiguous creation before a durable job is visible, and fully cleaned stopped-job UX. | Reload/close, lost acknowledged response, two jobs, scope/token changes, unknown storage locks, malformed/overflow metadata, stale completed generation/URN, replacement account, stopped/repaired/failed/completed states. Current discovery retains old pending holds and recent 24-hour terminals; it is not an immutable request ledger or exactly-once creation guarantee. Repaired-stopped states currently remain conservative support holds. |
| S03 | Partial — recorded display/cap editing corrected locally | Complete server-backed readiness and effective allowance in sender UI. | v2.101 removes inferred proxy dedication/health and invented warm-up/caps; shows recorded stops/UTC cooldown; preserves zero/unknown/legacy caps and sends only valid fields differing from editor opening. Full current paid-term/inbox/restore/permission/health blockers and effective allowance still need a verified server contract. Recorded metadata is not execution readiness; mutation context, unknown PATCH recovery and concurrent dirty edits remain separate. |
| S04 | Decision required | Easier sender onboarding via credentials/2FA or an extension. | Define authentication/session custody, browser challenge handoff, revocation, authorization, retry/unknown semantics and erasure before implementation. Existing supported path remains encrypted asynchronous cookie verification. |
| S05 | Partial / operational | Improve managed proxy assignment and operator workflow. | Managed leases/provider inventory already exist. Preserve paid/provider evidence, one-sender affinity, expiry and unknown resource outcomes. Automatic purchase, renewal or cancellation is a separate decision; do not remove those boundaries merely to imitate competitor UI. |

## 2. Lead generation and lead management

| ID | Status | Remaining change | Acceptance and edge cases |
| --- | --- | --- | --- |
| L01 | Decision required | Select a supported contract for Basic LinkedIn/Sales Navigator source collection. | Document permitted data, identifiers, pagination/rate and price limits, authentication, expected completeness and retention. Fixture-only parser success cannot enable collection. No real provider request or purchase is authorized by this plan alone. |
| L02 | Decision required | Post likers/commenters source adapter. | Preserve observed post/comment/actor references, source provenance and extraction time; distinguish liker vs commenter, missing identities, deleted/edited posts, partial pages, schema drift, duplicates and DNC. Public reply execution requires separate source-to-recipient binding. |
| L03 | Open, dependent on L01/L02 | Recurring source synchronization. | Stable cursors/watermarks, late arrivals, edited/deleted records, restart/checkpoint, partial/no results, backpressure, cancellation, auth/entitlement revocation and enrollment deduplication. Never silently claim complete post history. |
| L04 | Decision required | Network, events and groups sources. | A supported provider/data contract and permission model are prerequisites. Network is present in the observed Prosp source chooser; events/groups came from older material and were not in that session's five choices. |
| L05 | Decision required | Provider-backed B2B finder and profile enrichment. | Search filters, pagination, quotas/cost, returned evidence, permitted profile fields, missing/stale data, workspace isolation, cancellation and erasure. Do not manufacture sample prospects as successful results. |
| L06 | Partial — observable-token boundary implemented locally | Current server-context importer authentication/workspace fencing. | Context changes during file read, preview, edit, commit, close/reopen and unknown outcomes; preserve the original job/reference and prevent old-context rows/counts from appearing in the current view. v2.97 opening-token fences and v2.98 permission-resolved server workspace/actor/stored-UID/native-campaign request/response and transactional enrollment fences are implemented locally. Scoped source jobs require recorded original native campaign proof; legacy unbound jobs hold. v2.99 corrects the discovered A01 UID mismatch before shared profile recovery; immutable unknown-result/missing-record recovery, broader identity certification and global in-flight revocation remain open. |
| L07 | Partial | Complete lead review and organization UX. | Source/location/column filters, custom-field mapping, per-row validation and rejection export, selection across pages, large files, within/across-page duplicates, source aliases and current exclusions. Existing reviewed list membership/import/recovery remains available. |
| L08 | Open / migration | Review historical lost or unnormalized identity data. | Explicit census and provenance, conflicting current/saved aliases, historical contacted exclusions and native record replacement. No inferred ownership, auto-adoption or blanket backfill. Preserve uncertainty and provide a reviewed resolution path. |

## 3. Sequence, AI, voice and launch

| ID | Status | Remaining change | Acceptance and edge cases |
| --- | --- | --- | --- |
| Q01 | Protective admission implemented locally; migration open | Reviewed sender/node migration for in-progress leads. | v2.100 holds old/unproven versions and missing saved progress, qualifies binding and preserves terminal history. Only genuinely unbound/unacted queued roots get a first version. This does not implement migration or semantic equivalence; review original sender, frozen graph/content, invite/reply waits, due times and uncertain operations before explicit mapping. No automatic re-root/reassignment/replay. Same-version raw changes and rolled-back proof remain outside this guard. |
| Q02 | Decision required / open | Public reply/comment, follow, endorsement and InMail execution. | A UI node is not transport support. Establish exact recipient/action/source binding, current permission, evidence, limits, cancellation, unknown outcomes, dedupe and erasure before exposing it. No invented “10 fully live actions” claim. |
| Q03 | Open | Message-open and open-profile conditions. | Identify a supported evidence source; distinguish positive/negative/unknown/stale observations, polling deadlines and reply stops. Preserve existing typed data-column, connected and usable-email contracts. |
| Q04 | Open | Sequence-level add-tag node. | Data-only action with scoped tag/lead authority, immutable operation identity, duplicate delivery, deletion/erasure and graph/compiler compatibility. Inbox tag APIs do not by themselves implement this sequence node. |
| Q05 | Partial | Zero-delay companion text and longer revival sequences. | Zero delay alone does not override recipient reply history, freshness, outbound evidence, working hours or sender limits. Long sequences require validated finite graphs and reviewed action coverage; do not add uncontrolled loops. |
| Q06 | Decision required / open | Real AI generation and review on actual selected leads. | Choose provider/credential and cost policy; prepare outputs asynchronously, bind lead/sequence/prompt/source context, support revision/approval/invalidation, cancellation, unsafe output and unknown vendor outcomes. A 20-lead review grid is a proposed bounded UX, not an already verified product contract. |
| Q07 | Partial | Canvas recording/upload and approved voice artifact selection/preview. | Actual microphone/file handling, size/type/duration validation, quarantine, consent, current voice revision, selected lead/sequence binding, erasure and unknown outcomes. Existing buttons are explicitly unavailable; no dummy successful upload. |
| Q08 | Partial / operational | Complete dynamic voice and guided Studio user journeys. | Reuse existing provider/preparation/consent/artifact systems, with key custody, budget, retries and approved real-vendor evidence. Cache by complete permitted workspace/voice/script/context identity; a first-name-only cache must not mix tenants, revisions or consent. |
| Q09 | Open | Improve launch review of actual lead-specific outputs. | Current selected leads/senders, missing variables, approved message/audio, counts/exclusions, source status, current errors and exact version/digest. Existing preflight remains authoritative; displayed completion cannot confer execution permission. |

## 4. Inbox and attribution

| ID | Status | Remaining change | Acceptance and edge cases |
| --- | --- | --- | --- |
| I01 | Existing baseline; audit if changed | Improve saved snippet/tag UX only where a concrete gap is reproduced. | Preserve existing create/list/delete and compose insertion; member permissions, workspace switch, duplicate names, recipient context and erasure. Do not reopen the already-implemented baseline as wholly missing. |
| I02 | Open / provider decision | Meeting booking ingestion and attribution. | Supported Calendly/Cal.com or other contract, verified webhook authenticity, dedupe, cancellation/rescheduling, address/identity matching, unknown/ambiguous campaign attribution and deletion. Recorded booking evidence is not an invented conversion or revenue figure. |
| I03 | Partial / operational | Fresh reply/inbox and outcome fidelity. | Existing freshness, negative/reply stops and provider-accepted reporting remain. Authenticated integration completeness, delivery evidence and live pilot verification are separate from successful local tests. |

## 5. History, older data and operational release

| ID | Status | Remaining change | Acceptance and edge cases |
| --- | --- | --- | --- |
| O01 | Open | Read-only template history viewer. | Current authorized content reads, strict text/graph rendering, stale/replaced native identity, current-context invalidation, missing/corrupt/key/index/flag failures and no execution side effects. |
| O02 | Partial / separately reviewed | Restore and safe reactivation completion. | Reuse existing restore epoch/evidence protocols; reconcile payment/provider/resource/reply evidence, rehearse stopped recovery and explicitly reviewed new-epoch activation. No rolled-back backup may fabricate current consent, resource ownership, completed effects or execution permission. |
| O03 | Partial / migration | Remaining credential and unsupported older voice/proxy cases. | Source-qualified migration, key custody, native identity, selected evidence, quarantine, rollback/unknown outcomes and erasure. Existing migrations cover bounded supported data; unsupported legacy records require review rather than guessed conversion. |
| O04 | Operational | Storage, account recovery and infrastructure readiness. | Last recorded production readiness has R2 storage and password-reset custom-domain issues. Reverify storage/key access, AWS IAM and egress/network restrictions with separate authorization; this plan does not prove current live state. |
| O05 | Operational | Integration activation, controlled health monitoring and pilot. | Confirm supported provider/auth/paid term/proxy/reply evidence, effective limits, observability, rollback and a small authorized pilot. No production flags/grants/purchases or real provider/AWS calls are part of the current local continuation. |
| O06 | Open / operational | Security and combined release gates. | Inspect current CI/security findings, dependency backlog and protected checks; distinguish preexisting from introduced failures. Run appropriate combined backend/native/frontend/browser/build checks, review source/tests/docs, coordinate old-writer drain, then request the separately authorized release. |
| O07 | Release pending | Publish/deploy reviewed local changes when explicitly requested. | v2.95 is locally committed as 6fa7ca0; current continuation stays uncommitted and undeployed. Backend must support new discovery/context contracts before the new frontend is exposed; otherwise connection controls intentionally hold. Preserve flags, configuration, unrelated files and rollback capability. |

## Implementation order and completion rules

1. S01/S02 and bounded v2.97/v2.98 importer context repairs are locally reviewed; preserve their recorded limitations and evidence.
2. A01 source/security and final48-check documentation audit are complete locally. Q01 now has conservative version/step admission protection; reviewed migration remains open. Continue L06 durable outcomes and an explicit Q01 migration protocol as separate scopes, keeping original references and historical progress intact.
3. Improve S03/L07 where fixture-reproduced behavior can be completed locally.
4. Resolve provider/product decisions for L01/L02/L04/L05 and Q02/Q03/Q06 before dependent adapters/transport. Continue independent local work while waiting.
5. Complete separately scoped Q07/Q08/Q09 and attribution/history work against existing authorities and the chosen supported contracts.
6. Address O02–O06 and perform an explicitly authorized backend-first release/pilot.

Every completed entry needs concrete before/after behavior, files, regressions, database/browser evidence where relevant, independent review, migration/cutover requirements, known limits and remaining work. Do not mark a partial primitive, UI affordance, parser, unactivated provider adapter or successful synthetic test as full product parity.

The user requests stopping when weekly remaining allowance reaches 2%; the prior short-term 2% stop also applies. Check actual values before implementation and substantial verification, checkpoint unfinished reviews/tests, and resume only after the applicable actual reset. The requested 20 October 2026 22:30 IST continuation is a one-shot, not a daily recurring implementation permission.

## Related detailed backlogs

- [Latest Prosp flow audit](UNRAVLER_IO_PROSP_FLOW_AUDIT_AND_REPAIRS_RELEASE.md)
- [Current continuation fixes and evidence](UNRAVLER_IO_REMAINING_FIXES_LOG.md)
- [Product roadmap](MASTER_PRODUCT_ROADMAP.md)
- [Section-by-section outreach audit](UNRAVLER_IO_SECTION_BY_SECTION_AUDIT_2026_10_11.md)
- [Earlier outreach audit](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_OUTREACH_AUDIT_2026_10_10.md)
- [Eight-video implementation plan](OUTREACH_DRIPIFY_EIGHT_VIDEO_IMPLEMENTATION_PLAN.md)
- [Integration plan](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/OUTREACH_INTEGRATIONS_MASTER_PLAN.md)
- [Workspace lifecycle](UNRAVLER_IO_USER_LIFECYCLE_AND_IP_PROVISIONING.md)
- [Feature catalog](UNRAVLER_IO_FEATURE_CATALOG_AND_CAPABILITIES.md)
- [Architecture](UNRAVLER_IO_SYSTEM_DESIGN_AND_ARCHITECTURE.md)

This register covers the known outreach gaps recorded by those reviews. New provider behavior, production state and unaudited application sections can reveal additional work; “all known items listed” does not mean “the application is complete.”
