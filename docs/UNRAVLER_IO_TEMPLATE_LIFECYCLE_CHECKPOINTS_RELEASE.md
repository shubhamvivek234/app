# v2.88 creation and graph digest checkpoints

2026-10-19 IST. Verified local implementation extends the [v2.87 metadata foundation](UNRAVLER_IO_TEMPLATE_REVISION_CHECKPOINTS_RELEASE.md) to both creation endpoints and both reviewed graph-edit endpoints. Both source/test reviews approve the bounded change and final instrumented database verification passes. HEAD remains `e63bcfef3293eff407211096e764e4f516e3642b`. Earlier local v2.83–v2.87 and unrelated changes are preserved outside the recorded source/test/document/memory overlaps. No commit or deployment is included.

## Behavior and authority

Both legacy `POST /sequences/templates` and recoverable `POST /sequences/template-saves` now read back the exact inserted native BSON template and append a creation digest checkpoint in the same authorized shared-guard transaction. The legacy creation response retains its existing shape and nonrecoverable outcome semantics. Recoverable creation inserts its original receipt after the checkpoint; checkpoint, template, receipt and authority-counter writes roll back together. Creation checkpoint and receipt timestamps use UTC millisecond precision without rewriting the original template fields.

The common graph replacement helper appends an observed baseline if absent and a linked graph result after exact template BSON readback. Both legacy graph PATCH and recoverable graph POST therefore participate. Recoverable graph receipts follow the checkpoint inside their existing transaction. Current UID/user/role/erasure fences, snapshot/majority writes, original native identity/revision/full-record review and unknown-outcome handling are retained. No operation gains execution permission.

Original creation/graph receipt lookup and status remain ahead of compilation, current template lookup and checkpoint inspection. An earlier confirmed operation remains recoverable after deletion, native replacement or missing/corrupt checkpoints without replaying edits, creating templates, repairing history or backfilling checkpoints. Current original-actor authority is still required. Unknown outcomes retain their original request reference; legacy endpoints do not acquire durable client-request receipts.

## Checkpoint contract

The existing `outreach_template_revisions` collection retains the exact twelve-field schema and deterministic native-identity/revision IDs. This slice extends allowed events without adding fields:

| Event | Meaning | Parent contract |
|---|---|---|
| `created` | This participating creation transaction inserted and read back revision 1 | Revision exactly 1, both predecessor fields null; any existing same-native history rejects admission. |
| `graph` | A participating graph edit produced the next revision | Immediate original revision and exact original full-record digest. |
| `metadata` | Existing v2.87 metadata edit event | Same immediate predecessor contract. |
| `observed` | An existing revision was first observed without claimed earlier continuity | Both predecessor fields null; does not assert creation. |

Strict scalar/native identity/schema/UTC-ms validation and full retained parent validation apply to both graph and metadata. A retained creation assertion cannot coexist with an earlier revision of that native identity. Creation admission looks for any same-native record without filtering public ID, event or revision; malformed existing records cannot be hidden by those predicates. Existing rows are never rewritten or evicted. Exact BSON checkpoint readbacks are required.

Graph/metadata extension inspects at most 1,001 returned records and caps retained history at 1,000 per native identity, including new baseline/result entries. A creation contributes one checkpoint and obeys capacity. Corruption, contradictory/future history, missing or changed parents, original-hash mismatch and exhaustion hold the whole mutation. The collection still has only its default unique `_id` index; returned-row limits do not bound scanned work, BSON bytes or total storage.

No names, descriptions, graph content, raw JSON, credentials or Firebase UID are added to checkpoints. Public actor/workspace IDs, digests and timestamps remain linkable. Existing guarded workspace erasure purges creation/graph checkpoints and operation receipts, including after template deletion. Deletion itself still creates no tombstone/checkpoint.

## Verification

Evidence directory: `/tmp/unravler-template-lifecycle-checkpoints-5dnef34z`. These are selected template checks, not the full application suite. Root `.coverage` is preserved exactly at SHA256 `4b74da9b0ce92d241eb136c8d09b5716e661366ef11ff2f8a1bf666257de94ba`; instrumented data is private to the evidence directory.

| Final evidence | Result | Provenance |
|---|---|---|
| `backend-final.log/.xml` | 350 passed, zero skips, one existing warning; 1.63s | Eleven selected pure/API template modules, including 22 new lifecycle cases. |
| `native-final.log/.xml` | 454 passed, zero skips, one existing warning; 180.07s | Ten template native modules, including 41 new cases: 39 replica-set and two standalone checks. Fixtures stop their owned processes and remove their databases/storage. |
| Passing test identity comparison | 804 distinct selected checks | Zero passing overlap between the two runs; 63 new cases are included, not added again. |
| `coverage-pure.log/.xml`, `final-coverage.json` | Repeated instrumented 350 pure checks passed in 4.24s | Same identities as the backend run. Combined coverage merges these with the final instrumented native run. |
| Four runtime modules | 449/469 statements (95.74%), 167/182 branches (91.76%); 94.62% branch-inclusive combined, displayed 95% | Checkpoints, governance, saves and graph helpers; not whole-application coverage. |
| Checkpoint helper | 93/95 statements (97.89%), 44/46 branches (95.65%); 97.16% combined | Subset of the four-module coverage, not another measurement of application-wide coverage. |
| Independent final pure reruns | 49 passed each, zero skips, one existing warning; 1.07s and 0.84s | Both repeat 22 new plus 27 prior pure checkpoint cases; no additional distinct passes. Native tests were reviewed, not independently executed. |
| Python compile, scoped medium/high Bandit and diff checks | Passed; zero configured-severity Bandit findings | No broad dependency, live identity/provider or deployment claim. |

The 22 new pure cases cover created/graph event-parent contracts, native Int64-sensitive full-record hashes, strict timestamps/scalars, inactive transactions and contradictory creation roots. New native cases exercise all four endpoint combinations, exact template/checkpoint readback faults, checkpoint/receipt insertion rollback, original status/replay through missing/corrupt history, lost commit acknowledgements, public-ID reuse with new native identity, duplicate creation, graph/metadata competition, retained corruption/parents/capacity, standalone denial and actual guarded erasure.

Tests were written first: the initial 20 pure cases and four endpoint-combination native cases failed before wiring. Independent review then found that an observed revision 0 could coexist with a creation revision 1 and permit another edit. Two pure regressions failed before the retained-root guard was added; two real-database regressions verify metadata/graph rollback and byte preservation. The earlier native run of 452 passes predates that final fix and is historical evidence. An initial legacy-path run exposed a missing datetime import, corrected before subsequent runs; the initial Int64 test was corrected to assert preservation of native-sensitive digests rather than normalization. Historical logs are retained.

Both independent source/test reviewers approve the final seven Python-file hashes. Each independently reran 49 pure checks (22 new plus 27 prior); native execution is parent-owned. Scoped medium/high Bandit, Python compile and diff checks pass. No fresh whole-application, frontend/browser/build, production or provider-fidelity claim is made. Frontend source is unchanged; preceding v2.86 frontend/browser/build results remain historical.

## Limits, rollout and next work

This remains digest-only application-protocol history. It cannot recover template content and is not a WORM store, externally signed ledger or protection against rollback of the whole database backup. Raw writers and older writers can create gaps; a later participating edit records an explicit observed baseline rather than inventing continuity. Earlier saved receipts do not retroactively prove checkpoint capture.

The event vocabulary is expanded within stored contract version 1. Older v2.87 validators reject the new events, so deployment must drain or replace all affected creation/graph/metadata writers and readers together before a participating-history completeness claim. Mixed fleets can hold edits. No production migration, historical backfill, repair, purge or capacity bypass was run.

Deletion continuity, content snapshots, history read/view APIs, compound indexes, pagination, retention and restore remain unfinished. Define deletion continuity and bounded history storage/read contracts next, before content recovery or a history viewer. Private visibility, ownership transfer and external sharing remain separate product contracts; source/filter, team/sender and operational pilot gates remain open in the [implementation plan](OUTREACH_DRIPIFY_EIGHT_VIDEO_IMPLEMENTATION_PLAN.md).

The final manifest records source/document/evidence hashes, baseline preservation, eight synchronized Desktop pairs and document links. Session memory is updated last. No commit, push, deployment, production migration, live-flag change, real provider/AWS call, grant or purchase is performed. Headroom tools were unavailable; no token savings are claimed.
