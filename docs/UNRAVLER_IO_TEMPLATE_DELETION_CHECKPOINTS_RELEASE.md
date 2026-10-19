# v2.89 template deletion continuity

2026-10-19 IST. Verified local deletion continuity extends the [v2.88 creation/graph checkpoint foundation](UNRAVLER_IO_TEMPLATE_LIFECYCLE_CHECKPOINTS_RELEASE.md). Both independent source/test reviews approve the bounded change and final database verification passes. HEAD remains `e63bcfef3293eff407211096e764e4f516e3642b`. Earlier local v2.83–v2.88 and unrelated work are preserved outside the explicitly recorded source/test/document/memory overlaps. No commit or deployment is included.

## Result and transaction boundary

Both legacy reviewed DELETE aliases and the recoverable deletion POST now record a terminal digest checkpoint inside their existing authorized workspace transaction. Their common removal helper receives the current actor and UTC millisecond timestamp privately. It checks the original native/revision/full-record review, performs the literal original-row deletion, verifies native absence, then appends the terminal before any recoverable operation receipt is inserted. Public request/receipt formats remain unchanged; legacy deletion remains nonrecoverable by request ID.

Template deletion, an absent observed baseline if needed, terminal insertion, recoverable receipt and user/role/guard authority writes commit or roll back together. Exact BSON checkpoint readbacks are required. Role/UID/erasure authority, shared guard, snapshot/majority behavior and unknown-result handling are retained. No provider action or execution permission is added.

An original historical deletion receipt and explicit status still return before policy parsing, current template lookup or checkpoint inspection. They do not replay deletion, repair/backfill missing history, or delete a replacement or restored original. Current original-actor authority is still required. A missing status remains unconfirmed and does not create a terminal.

## Same-revision terminal contract

The existing `outreach_template_revisions` collection retains its exact twelve fields and stored contract version 1. Allowed events gain `deleted`. The original ordinary checkpoint at revision N and the terminal deliberately share N, with distinct deterministic IDs:

- The ordinary record retains the original template full-record digest.
- The terminal uses the `template-deletion-checkpoint-v1` ID domain and `template-deletion-result-v1` result-digest domain.
- Its `predecessor_revision` equals N and `predecessor_review_digest` equals the exact original full-record digest. The terminal result digest binds workspace, public template ID, native identity, N and that parent digest.
- Strict schema, native scalars, plain strings, actor and UTC-ms validation apply; terminal identity/result hashes are recomputed. Revision 0 and the final JavaScript-safe revision are supported without incrementing or overflowing.

A terminal is an application deletion result, not a new content revision. A future history reader must distinguish event kind and terminal identity rather than treating revision alone as a unique content key. No history reader is introduced here.

The shared append path validates the original and all retained ordinary parent/root/hash relationships before adding an absent baseline and terminal. A creation assertion cannot coexist with an earlier revision. Existing same-native terminal history holds further metadata edits, graph edits and deletion, including a raw-restored original at a newer revision; malformed terminal IDs/hashes also hold without repair. A new native template reusing a public ID has a separate history. Existing checkpoints remain byte-for-byte unchanged.

The 1,000-record native-identity cap includes baseline and terminal; at most 1,001 returned rows are inspected. Corrupt/future/missing-parent/mismatched history and capacity exhaustion roll back ordinary deletion. The cap does not bound unindexed scan work, BSON bytes or total storage. Only the default unique `_id` index exists. Ordinary deletion can therefore be held at capacity. The separate guarded workspace/account erasure protocol remains available and purges terminal or capacity-held history; no cap bypass, eviction or operator repair is introduced.

No template text, graph, raw JSON, credentials or Firebase UID is copied to the terminal. Public actor/workspace IDs, timestamps and digests remain linkable metadata. Workspace erasure already includes the collection and recoverable deletion receipts, including after the template itself is absent.

## Verification

Evidence directory: `/tmp/unravler-template-deletion-checkpoints-u48ywg2a`. Root `.coverage` remains exactly the saved `root-coverage-before`, SHA256 `4b74da9b0ce92d241eb136c8d09b5716e661366ef11ff2f8a1bf666257de94ba`; measurement data is private to this directory. These are selected template checks, not the full application suite.

| Final evidence | Result | Scope and overlap |
|---|---|---|
| `backend-final.log/.xml` | 368 passed, zero skipped, one existing warning; 4.48s | Twelve pure/API template modules, including 18 new pure cases; instrumented. |
| `native-final.log/.xml` | 491 passed, zero skipped, one existing warning; 194.45s | Eleven native template modules; collected before eight additional test controls were appended. Includes the initial 37 new native cases. |
| `native-expanded.log/.xml` | 45 passed, zero skipped, one existing warning; 23.79s | All final new native cases: 43 replica-set and two standalone. Exactly 37 passing identities overlap the broad native run; eight are additional. |
| Identity union | 499 distinct native and 867 distinct overall selected passes | 491 + 45 - 37 = 499; pure/native overlap is zero. This is not a single fresh 499-native run. The 63 new cases (18 pure + 45 native) are included, not added again. |
| `final-coverage.json` | 352/365 statements (96.44%), 125/134 branches (93.28%); 95.59% branch-inclusive combined, displayed 96% | Merges the three instrumented runs across checkpoint, governance and deletion runtime modules; not whole-application coverage. |
| Checkpoint helper | 112/114 statements (98.25%), 48/50 branches (96%); 97.56% combined | A subset of the three-module coverage, displayed 98%. |
| Independent pure reruns | 67 passed each, zero skipped, one existing warning; 0.88s and 1.01s | Each repeats 18 new plus 49 prior pure checks. Native tests were reviewed, not independently executed. |
| Compile, scoped medium/high Bandit, diff checks | Passed; zero configured-severity Bandit findings | No broad dependency/security, production or live-provider claim. |

Tests were written first: 18 pure cases and four native endpoint/baseline combinations failed before implementation. Initial native verification passed 37 cases in 17.63s. The second review requested eight further native controls for malformed stored terminals, metadata/deletion competition and exact-capacity success; those supplement the broad run rather than replacing its earlier cases. Historical logs are retained. Two existing native test files only change three deletion-related expectations to include the terminal explicitly; their earlier assertions remain.

The new native controls cover both deletion paths with older and created roots, exact native parent hashes, final-revision Int64 deletion, failures after baseline/terminal/receipt insertions and readbacks, original acknowledgement loss, original receipt recovery through missing/corrupt history, restored same-native holds across all three mutations at original/newer revisions, current/future/parent/capacity contradictions, graph/metadata deletion races, duplicate deletion, actual erasure and standalone denial.

Both independent source/test reviews approve seven Python-file hashes. Each independently reran 67 pure cases (18 new plus 49 prior); native execution is parent-owned. Python compile, scoped medium/high Bandit and diff checks pass. Frontend source and public receipt contracts are unchanged. No fresh frontend/browser/build, whole-application, production or live provider/Firebase fidelity claim is made; earlier frontend/browser/build results remain historical.

## Rollout limits and next work

This completes bounded local digest capture for participating creation, metadata, graph and deletion operations. It does not supply content snapshots, a complete historical backfill, history UI/API or restore. Digest links cannot recover content. Application append behavior is not WORM storage, external authentication or protection from rollback of the whole database backup; older/raw writers can create gaps and remove evidence outside this protocol. Removing terminal evidence or rolling back its backup can remove these holds; outside-backup reconciliation remains separate.

The new event remains within stored version 1, so older v2.88 validators reject it. Affected creation/edit/deletion writers and readers must be drained or replaced together before claiming participating-history completeness. Earlier receipts do not retroactively prove terminal capture. No production migration, historical backfill, raw restoration, repair or activation was performed.

Next, define bounded history storage/read contracts, including native/event identity, compound indexes, pagination, capacity and retention/erasure behavior, before storing recoverable content or building a viewer/restore flow. Private sharing/transfer and broader source/filter, team/sender and operational pilot gates remain separate in the [implementation plan](OUTREACH_DRIPIFY_EIGHT_VIDEO_IMPLEMENTATION_PLAN.md).

The final manifest records frozen source/document/evidence hashes, baseline preservation, eight Desktop pairs and document links. Session memory is updated last. No commit, push, deployment, production migration, live-flag change, real provider/AWS request, grant or purchase is performed. Headroom integration was unavailable; no token savings are claimed.
