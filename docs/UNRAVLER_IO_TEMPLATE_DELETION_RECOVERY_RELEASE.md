# Unravler.io v2.82 — Recoverable reviewed template deletion

Updated: 2026-10-18 IST. Bounded local implementation on baseline `090ae86`, preserving the approved uncommitted [v2.81 graph recovery](UNRAVLER_IO_TEMPLATE_GRAPH_RECOVERY_RELEASE.md), earlier canvas/landing/auth changes and unrelated local work. This report does not establish a fresh deployment or remote CI result.

## Customer behavior

Deleting a reviewed custom template now records its original outcome. If the response is lost, **Check original deletion status** checks the same original request under current credentials. An exact historical receipt confirms **Original template deletion confirmed**, then reloads the current catalog. A later replacement with the same public ID remains visible; historical confirmation never removes a replacement from the browser or database.

Preparation, transport and status checking block competing template use, metadata editing, sequence editing and deletion. Missing or uncertain results remain held without automatic POST replay or a fresh request ID. Missing GET404 can remain held indefinitely if no receipt committed. References and holds remain view-memory-only: leaving/unmounting/tab/browser loss can discard them. Persistent update/deletion references are subsequent work; existing creation-reference sessionStorage is unchanged.

## Exact original request and historical receipts

Dedicated `/sequences/template-deletions/context`, POST and original-reference GET require `sequence:delete`. The context binds a distinct `template-deletion-scope-v1` workspace/public-actor/original-authenticated-UID scope. A plain canonical UUID and exact whole-operation UTF-8 JSON SHA-256 identify the original request; browser/API/core enforce the complete 8,192-byte input bound.

Only a new request parses version1 JSON. It requires exactly contract version, workspace, template ID and original revision/full-BSON-review/native-identity/inner-deletion-scope fields. Duplicate keys, coercion, extra fields and unsupported scope deny. Graph execution compatibility is not a deletion prerequisite: a faithfully reviewed malformed legacy template can still be removed.

Stable envelope/scope/UUID/byte/hash validation and current deletion authority precede receipt lookup. An existing same-reference/input receipt returns before new-policy parsing or current-template lookup; conflicting input returns409. An original deletion remains recoverable after absence, recreation, later metadata/graph changes or another deletion, without removing or changing the current replacement. Receipts never reconstruct earlier unknown legacy DELETE outcomes.

## Transaction, identity and privacy

The existing shared workspace guard/snapshot/majority transaction fences current unique native user/member-or-owner, original Firebase UID and erasure authority using counter writes. Current authority is rechecked for first deletion, same-original retry and status GET. A duplicate authenticated UID under another public actor also denies access.

The common guarded deletion helper retains exact original native identity/revision/full-row review and literal full-row CAS. A new same-transaction native absence readback rejects an unexpected retained original record. The new receipt insertion and exact BSON reread share that transaction; deletion, receipt and authority counters roll back together on failure. The legacy reviewed DELETE aliases retain their prior public receipt shape and gain this absence check. They do not create new recoverable receipts. New POST paths cannot reach an older DELETE-only server handler.

`outreach_template_deletions` uses a deterministic scoped UUID-derived `_id` and MongoDB's built-in unique `_id` index, without TTL. Its strict minimal record contains original reference/input/template/revision/full-row/native-identity/expected-inner-scope hashes, status, public actor reference and a UTC-millisecond audit time. Native int/Int64 revisions include the final JavaScript-safe integer; bools, unexpected fields and malformed BSON scalar/timestamp/schema values deny confirmation. Actual guarded erasure purges this collection and blocks later recovery.

No template name, description, graph, raw JSON or separate Firebase UID field is stored. Public actor IDs can coincide with legacy identity values; references and hashes remain linkable metadata. These are trusted application/database assertions, not signed external evidence, immutable version history or restore-completeness proof. Status/retry can write guard/authority counters. Backup rollback, missing outside-backup facts, raw writers and undrained older processes remain limits.

## Browser fencing

The gallery copies and freezes the complete original review before asynchronous work. Fresh context and UTF-8 hashing finish before a validated single UUID/reference is admitted; the reference is retained before one POST. Exact HTTP200 receipts must match both the outer original locator/input and inner native/revision/full-row scope.201/202, malformed JSON, extra fields and mismatched receipts remain unconfirmed.

Synchronous preparation/status latches prevent overlapping clicks and dependent editor/use actions. Original view generation, mount and per-request token checks fence each asynchronous response. Pretransport context loss permits **Cancel deletion preparation** with no submitted deletion; definite preparation failure permits a new deliberate preparation without retaining an original request reference.

Recovery uses current credentials plus a fresh exact context matching the original workspace/outer scope before original-status GET. Normal token refresh works; a foreign context never reads its prior outcome. Token/view/mount changes during context, hashing, POST or status cannot confirm an original result. Successful historical confirmation uses exact200/current-token catalog refresh; catalog loading/failure/absence itself never proves deletion.

## Verification

Final affected backend selection: 199 passed, zero skips, one existing warning in44.85 seconds =101 new (39 pure/62 native) plus98 prior governance checks. Controls include identical/conflicting originals, later replacements/edits/deletion, initial/status/retry authority changes and post-snapshot revocation, duplicate UID, original native/content/revision drift, receipt and absence-readback faults, transactional rollback, actual guarded erasure ordering/purge, actual standalone denial, simulated commit-ack loss, strict HTTP contracts and final JS-safe Int64 receipts. Races against actual metadata, graph and legacy deletion writers have one winner.

Whole frontend: 514 passed across 55 suites in 12.55 seconds. The 78 affected checks across three suites pass in 2.095 seconds and cover frozen originals, one request, held unknowns, exact receipts, same-identity refreshed-token recovery, foreign scopes, delayed JSON/hash departures, valid competing editors, UUID validation and replacement-preserving historical refresh. Independent frontend review approves and independently reruns all 78. Independent Python review approves the source and added tests; 39 new pure checks independently pass in 1.23 seconds.

Fresh broad application checks pass 4,079 with 2,071 historical/opt-in skips, six sandbox deselections and 13 existing warnings in 301.95 seconds. All 44 compiled synthetic browser journeys pass, including four deletion journeys (one net addition) with real Unicode workspace/whole-input SHA checks, lost-response historical confirmation with a current replacement, missing404 holds and strict202 denial. The CI-mode production build passes in 81.44 seconds with existing warnings. Python compilation, configured medium/high scoped Bandit (zero findings) and diff checks pass.

Frontend coverage verifies all 78 affected checks. The new recovery helper has 100% statement/line/branch/function coverage; the two selected deletion utilities combine to 95% statements/100% lines/97.36% branches. A separate instrumented controller selection covers the new deletion/status control region (current lines590–673): 88/92 statements (95.65%),66/69 executable start lines (95.65%),67/71 branch arms (94.37%) and10/10 functions. This is the selected deletion region, not whole-page coverage.

Backend coverage passes 641 overlapping template checks with one existing warning in 186.45 seconds: 443/511 statements (87%) combined, new deletion receipt core 106/108 (98%), shared governance 125/132 (95%) and sequence API 212/271 (78%). The complete 33-module native suite passes 1,279 checks with zero skips and three existing warnings in 662.50 seconds; CI minimum 1,279 is verified. Broad/native passing-ID overlap is zero, giving 5,358 distinct backend passes; all 199 affected checks are in that union. Focused/coverage selections are not added again. Browser/transport fixtures are synthetic loopback APIs and do not establish authenticated provider/source or live pilot fidelity.

Private backup/evidence: `/tmp/unravler-template-deletion-recovery-ItJCDD`. Final artifact verification checks 17 frozen source/test/config/document hashes, 49 preserved earlier-source hashes, 1,761 protected starting files (1,753 tracked), nine historical unrelated fingerprints, 26 byte-identical Desktop pairs from 23 source documents and 336 local links. Owned test services are stopped and browser port4179 is closed; user Mongo1735/Redis1742, root coverage, wedding assets and nested worktrees remain preserved. `final-verification.json` records final independent numerical/document approval and the last-written session-memory hash.

## Rollout and remaining work

This continuation remains local: no commit/push/deploy, production migration, live/conditional flag change, grant, purchase or real provider/AWS call. A separately authorized rollout must drain older writers and use matching frontend/backend contracts; the new receipt collection must remain included in erasure. Older clients retain their earlier nonrecoverable reviewed DELETE behavior.

Next: persistent metadata/graph/deletion recovery references, sharing/ownership and immutable revision history. Broader source/recipient fidelity, team/sender governance, security/legacy migrations, authenticated restore/reconciliation/reactivation, controlled integration/health/IAM-egress checks and an actual pilot remain open.
