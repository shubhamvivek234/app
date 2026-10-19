# v2.87 metadata digest checkpoints — history foundation

2026-10-19 IST. The bounded metadata checkpoint implementation is complete locally. It remains uncommitted and undeployed at HEAD `e63bcfef3293eff407211096e764e4f516e3642b`, alongside approved local v2.83–v2.86. Complete template content history and restoration remain unfinished. This report supersedes the unfinished-documentation status in the [original continuation checkpoint](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_TEMPLATE_REVISION_CHECKPOINTS_CHECKPOINT.md).

## Result and transaction boundary

Successful authorized metadata replacements now append digest checkpoints in `outreach_template_revisions`. Both the legacy reviewed PATCH and recoverable metadata POST use the existing common replacement helper. After exact BSON template readback, the checkpoint helper records an absent observed baseline and the linked metadata result before any recoverable receipt insertion. Existing UID, role, erasure and shared-guard authority remains unchanged. Template, checkpoint, receipt and authority-counter writes commit or roll back together in the existing snapshot/majority transaction. The helper rejects calls without the guarded database wrapper and an active transaction.

An `observed` checkpoint records the current native template revision and full-record digest without inventing creation or earlier history. A `metadata` checkpoint records the resulting revision/digest and links the exact original revision/digest. Native-identity hashing distinguishes replacement records that reuse a public template ID. Existing checkpoints remain byte-for-byte unchanged; only absent baseline/result rows are inserted, with exact BSON readbacks.

Original historical receipt replay and status paths return before checkpoint insertion. Recovering an earlier metadata result therefore does not edit the current template or append another checkpoint. Public receipt formats, template review contracts, graphs, campaign copies and frontend behavior remain unchanged.

## Stored data and strict validation

The collection has twelve fields per record: `_id`, `contract_version`, `workspace_id`, `template_id`, `identity_digest`, `revision`, `review_digest`, `event`, `predecessor_revision`, `predecessor_review_digest`, `recorded_at`, and `recorded_by`. The deterministic ID hashes the contract namespace, workspace, native identity and revision. Validation requires the exact schema, plain strings, JavaScript-safe stored integer/Int64 revisions, UTC millisecond timestamps and valid event/predecessor relationships. Expected-context booleans/floats and BSON Code strings are rejected.

No names, descriptions, graph content, raw operation JSON, credentials or separate Firebase UID are copied. Workspace/public actor IDs, hashes and timestamps remain linkable metadata. Normal guarded workspace erasure includes this collection, including checkpoints whose template has subsequently been deleted. No retention exemption or TTL is introduced.

The identity query uses workspace and native identity without hiding malformed records behind redundant public-template-ID or numeric-revision filters. It inspects at most 1,001 returned rows and permits at most 1,000 retained checkpoints per native identity, including newly inserted entries. Every retained row must match the exact context and schema; duplicate/future revisions are rejected. Every declared metadata parent must exist with the exact predecessor digest, and the current checkpoint must match the actual original template. Missing parents, corruption, a restored lower revision, mismatches and capacity exhaustion hold the edit without repair, reinterpretation or eviction.

## Verification and provenance

Evidence is retained in `/tmp/unravler-template-revision-checkpoints-jg1s25il`. These final runs preceded the usage pause; the continuation rechecked their frozen source hashes and preserved artifacts instead of repeating finished code work.

| Final evidence | Verified result | Scope |
|---|---|---|
| `backend-final.log`, `backend-final.xml` | 328 passed, 62 skipped, one existing warning; 2.80s | Selected backend suite, including 27 new pure checkpoint cases. All skips are historical opt-in erasure cases; this is not a full application run. |
| `native-final.log`, `native-final.xml` | 122 passed, zero skipped, one existing warning; 48.20s | 20 new checkpoint cases, 51 metadata and 51 recoverable metadata-update cases against local Mongo. |
| `coverage-final.log`, `final-coverage.json` | 47 passed, zero skipped, one existing warning; 12.58s | 27 pure plus 20 native cases already included above; these overlap and are not additional passes. |
| Selected checkpoint core coverage | 75/78 statements (96.15%), 39/42 branches (92.86%); 95% branch-inclusive combined | New checkpoint helper only, not the whole application. |
| Independent final pure reruns | 27 passed each, zero skipped, one existing warning; 0.88s and 1.04s | `independent-checkpoints-final.log/.xml` and `reviewer-final-pure.log/.xml`; these repeat parent cases. |
| Python compile, scoped medium/high Bandit, diff check | Passed; zero configured-severity Bandit findings | Final reviewed source; no broad dependency/security or deployment claim. |

Both independent source/test reviews approve the final bounded foundation. The final five source/test hashes are recorded in `reviewer-source-report.json`. The native controls were independently reviewed; native execution remains parent-owned. Seven red regressions in `review-red.log` demonstrated the context-type, active-transaction, retained-parent and same-identity corruption gaps before their fixes. Earlier 24-pure/117-native evidence is historical and superseded.

Native regressions cover atomic baseline/result insertion, byte preservation, metadata/recoverable paths, replay, native replacement, malformed/current/future/parent mismatches, capacity, authority and edit/erasure races, rollback, readback corruption, transaction-unavailable failure and unknown commit acknowledgement. Local synthetic native identities do not establish real Firebase/provider fidelity. Owned Mongo fixtures stopped normally.

Frontend source is unchanged. The preceding v2.86 results of 680 frontend tests, 53 compiled synthetic browser journeys and a 70.29s production build remain historical; no fresh frontend/browser/build run is claimed here. Root `.coverage` is preserved exactly at SHA256 `4b74da9b0ce92d241eb136c8d09b5716e661366ef11ff2f8a1bf666257de94ba` and matches `root-coverage-before`. Coverage for this slice is private to the evidence directory.

## Limits and rollout requirements

Application-protocol append-only records are a consistency foundation. They do not provide WORM storage, external signatures, authenticated evidence outside the database, protection when the entire backup is rolled back, or completeness against uncoordinated raw writers. Hash links do not recover content. No complete historical backfill, creation/graph/deletion capture, content snapshots, history API/viewer, restore/revert, private visibility, ownership transfer or external sharing is implemented in this slice.

The collection currently has only the default unique `_id` index. The returned-row limit does not bound scanned database work, BSON bytes or total storage. Production-scale compound indexes, query/pagination behavior and retention must be designed before broader rollout. Capacity exhaustion deliberately holds metadata editing; operators must not erase or evict checkpoints to bypass it.

Older metadata writers must be replaced or drained before claiming participating edits are checkpointed. Graph edits still create uncheckpointed revisions; a subsequent metadata edit records an explicit observed baseline rather than inventing continuity. Existing historical receipts remain authoritative only for their original operation and do not establish full revision history. No production migration or activation was performed.

## Preservation and next work

The final evidence manifest records frozen source/test/document hashes, the original 1,810-file baseline, intentional differences, eight Desktop documentation pairs and local-link checks. Approved local v2.83–v2.86 and unrelated files, worktrees, root coverage and user services are preserved outside the explicitly recorded metadata/erasure/document/memory overlaps. The original checkpoint manifest retains its historical pause hashes; the final manifest records the updated checkpoint document. Session memory is updated last.

Next, capture creation and graph revisions under the same authority and atomicity rules, defining deletion continuity explicitly. Then design content snapshots, strict history read/view contracts, indexing/pagination and retention before restoration. Public/private sharing and transfer remain separate product decisions. Source/filter fidelity, team/sender governance and operational pilot gates remain open as tracked in the [implementation plan](OUTREACH_DRIPIFY_EIGHT_VIDEO_IMPLEMENTATION_PLAN.md).

This continuation performs no commit, push, deployment, production migration, live-flag change, real provider/AWS request, grant or purchase. No Headroom integration was available; no token savings are claimed.
