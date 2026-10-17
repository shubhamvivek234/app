# Unravler.io v2.80 — Recoverable template metadata updates

Updated: 2026-10-17 IST. Local, uncommitted and undeployed on main at `54378a0913f87b8fd0c01fbb98e8e56c39a2c19a`. This follows [reviewed graph editing](UNRAVLER_IO_TEMPLATE_GRAPH_RELEASE.md) and extends [reviewed name/description editing](UNRAVLER_IO_TEMPLATE_METADATA_RELEASE.md). Prior backend deployment remains deferred by the user. No current coherent production-fleet claim is made.

## User behavior and bounded scope

Save details now submits a recoverable original name/description update. A committed edit and its minimal historical receipt are atomic. If its response is lost, **Check original update status** reads that original receipt; no automatic POST replay or fresh request ID is admitted while unknown. Recovery reports **Original template update confirmed**, then fetches the current gallery, whose details may reflect later edits or deletion.

Names/descriptions, original native/revision/full-row proof, exact text validation, current sequence:update/member-or-unique-owner authority and campaign-copy preservation retain v2.78 behavior. Graph editing/deletion remain their existing reviewed contracts without these new outcome receipts. Sharing, immutable content history and old unrecorded outcomes remain separate work.

## Backend contract

New context GET, POST and original-reference GET use /sequences/template-metadata-updates. Strict outer HTTP fields bind contract1, resolved workspace, a canonical UUID, operation scope and input digest. A distinct template-metadata-update-scope-v1 namespace binds original actor/UID/workspace; it cannot substitute the inner original metadata-review scope.

Before a receipt lookup, validate only stable envelope/scope/reference and exact plain-string UTF-8 input size/hash, then current authority. Input is at most8,192 UTF-8 bytes; SHA-256 binds exact JSON including whitespace. Existing receipt recovery precedes current template lookup and current metadata-policy parsing. Same request/input returns the historical result after later metadata/graph changes, deletion or native replacement; conflicting input returns409. A new request alone parses exact version1 fields, rejects recursive duplicate JSON keys and reuses strict original metadata validation.

The legacy metadata service now shares an in-transaction replacement helper with the recoverable service. Both acquire the existing workspace guard/snapshot/majority transaction and authorize original UID/current unique native user/member-or-owner/erasure counters before applying it. The helper preserves captured literal full-row CAS, exact BSON readback, full-record bound and final JS-safe revision behavior. It propagates failures to the caller's transaction; no nested commit precedes receipt insertion.

New outreach_template_metadata_updates uses a deterministic scoped UUID-derived _id and MongoDB's built-in unique _id index, with no TTL. Minimal allowlisted receipts retain original input/template/native identity/revision/full-row proof, original inner review scope and resulting revision/review hash, plus actor reference and UTC-millisecond creation audit. Names, descriptions, graphs and raw JSON are excluded. No separate authenticated Firebase UID field is stored; actor_id retains the existing public user identifier, which can coincide with legacy identity values. References/digests remain linkable metadata, not anonymization or signed external evidence.

Stored receipts require exact schema/scalar types, JS-safe integer/Int64 revisions with new_revision=revision+1 and the deterministically expected original inner review scope. Exact receipt BSON reread must match the prepared record. Template replacement, receipt insertion and authority counters roll back together on failure. Actual guarded erasure purges this collection and blocks later recovery. Status/retry reauthorize current access even when the template no longer exists; status reads can advance guard/authority counters.

A receipt confirms the original recorded application update, not current template existence/content, immutable versions, provider outcomes or execution permission. Backup rollback/raw writers and database trust remain limits; no authenticated outside-backup completeness claim is added. The retained legacy PATCH has unchanged response behavior and creates no new receipt. New POST paths cannot fall through to that older handler.

## Browser recovery and limits

The editor freezes copied original review/template ID/name/description JSON before hashing, admits one UUID only after preparation and retains a memory-only reference before POST. Exact HTTP200 receipts must match original outer scope/reference/input and inner native/revision/review proof, next revision and a valid resulting server digest. Server digests are assertions, not browser reconstruction or signatures.

Single-flight preparation/status latches, original props/mount and token checks fence dependent awaits. Definite preparation failure permits correction without a request ID. Pre-POST context loss enters a stopped state with safe Cancel and an explicit no-submission message. An explicit status check captures current credentials, validates a fresh context against the retained original workspace/scope and fences its completion; normal token refresh can recover the same original UID, while a foreign context never queries its outcome.

Malformed/extra receipts, HTTP201/202, network/JSON failures and missing404 stay held; catalog resemblance or absence cannot confirm the original. There is no browser write replay, retry/cancel protocol or fresh-UUID escape from unknown state. GET-only404 may remain held indefinitely if no receipt committed. View/unmount/tab/browser loss discards this memory-only locator and hold; same-tab persistence for updates is not implemented. Existing v2.77 creation-reference sessionStorage remains untouched. Cross-tab/raw-script coordination and old-writer drain are still required limits.

## Verification and provenance

Final focused backend:165 passes, zero skips, one existing warning,38.09 seconds =86 new (35 pure/51 native) plus79 prior metadata checks. Native controls cover identical/conflicting requests, later metadata/graph/delete/native changes, original status/retry, current and post-snapshot role/UID/erasure revocation, strict persisted receipts and valid-shaped readback corruption, rollback of template/receipt/counters, two actual guarded-erasure orderings, actual erasure purge, standalone denial, simulated commit-ack loss, old-API negative control and final JS-safe BSON Int64 recovery.

Independent backend review approved source/tests after correcting deterministic inner-scope validation;35 pure checks independently passed. Independent frontend review approved the corrected current-token recovery and safe stopped-preparation exit;40 checks across three suites independently passed. Earlier runs with missing routes, an invalid graph fixture and an _id index-information expectation are historical, corrected without weakening source controls.

Fresh whole frontend passes458 checks across53 suites in15.556 seconds. The40 affected frontend checks also pass under coverage in5.227 seconds: selected editor/helper94.73% statements,100% lines and92.79% branches. Backend coverage passes440 overlapping checks in162.61 seconds; combined360/421 statements (86%), new receipt core104/107 (97%), shared metadata74/75 (99%) and sequence API182/239 (76%). Focused/coverage checks are not added again to broad/native totals.

All42 compiled synthetic-API browser journeys pass in52.312 seconds, with four revised metadata journeys including one additional missing-status hold. The CI-mode production frontend build passes in92.26 seconds with existing warnings. Python compilation, configured medium/high scoped Bandit (zero findings) and diff checks pass. Fresh broad application checks pass3,998 with1,950 historical/opt-in skips, six sandbox deselections and13 warnings in315.14 seconds. Complete31-module native checks pass1,158 with zero skips and three warnings in619.38 seconds, meeting CI minimum1,158. Zero broad/native passing-identity overlap gives5,156 distinct backend passes; all165 affected passing IDs belong to that union. Synthetic browser APIs do not establish authenticated live/provider/source fidelity. Remote CI/security/protected-check enforcement remains separate.

Private backup/evidence: /tmp/unravler-template-metadata-recovery-LiU5Ml. Verification checks19 frozen source/test/config/document hashes,29 preserved earlier-release hashes,24 byte-identical Desktop pairs from21 sources,324 local links,1,727 protected tracked files and nine historical unrelated fingerprints. Final-verification.json records final passing identities/overlap, independent numerical/document approval and cleanup. Session memory is written last after final approval.

## Rollout and next work

Keep work local. Before a separately authorized rollout, drain older writers and ship matching backend/frontend contracts with the new receipt collection participating in erasure. Old unknown PATCH operations have no retroactive receipt and cannot use this recovery path.

Next: sharing/ownership requirements, recoverable graph/delete outcomes, persistent update references and immutable revision history. Broader source/recipient contracts, team/sender governance, security/legacy migration, authenticated restore/reconciliation/activation, live health, IAM-egress and actual pilot gates remain open. No commit/push/deploy, production migration, provider/AWS request, grant, purchase or live/conditional flag change occurred.
