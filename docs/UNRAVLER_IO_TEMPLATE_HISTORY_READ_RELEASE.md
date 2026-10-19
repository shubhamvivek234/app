# v2.90 guarded template digest-history reads

2026-10-19 IST. This local slice extends the [v2.89 deletion-continuity foundation](UNRAVLER_IO_TEMPLATE_DELETION_CHECKPOINTS_RELEASE.md) with explicit index preparation and guarded, paginated digest-history reads. It adds no frontend, content recovery or restore operation. HEAD remains `e63bcfef3293eff407211096e764e4f516e3642b`; earlier local v2.83–v2.89 and unrelated work are preserved outside the recorded overlaps. No commit or deployment is included.

## Read and authority contract

`GET /sequences/templates/{template_id}/revision-checkpoints` requires an authenticated current user, the explicit original `identity_digest`, optional decimal `page_size` from 1 through 25 (default20), and optional cursor. Unknown or duplicate query keys, noncanonical sizes and malformed references are rejected. Successful responses use `Cache-Control: no-store`.

Current native user/UID uniqueness, active member or actual owner, sequence-read permission, identity tombstone and open workspace are checked in the shared guard/snapshot-majority transaction. The access inspector binds every observation to that transaction's session. Owners, admins, editors, viewers and clients can read within their current workspace; creator attribution grants no extra access. The handler deliberately uses authenticated identity followed by the transactional permission check, avoiding the generic pre-handler role conversion that raises on malformed roles.

Successful GETs write the shared guard and user/member-or-owner authority counters to fence changes. Ordinary authentication hydration can also write existing user/workspace state. The history handler does not write templates, checkpoints, receipts, indexes, grants or execution state. Unknown transaction acknowledgements return a sanitized503 without a history payload; a repeated GET rechecks current authority rather than replaying a domain operation. Standalone Mongo cannot disclose this transactional history.

The explicit native identity remains authoritative after deletion or replacement of the public template ID. A read never silently follows the replacement, requires no surviving current template, and does not search for other native identities. This API alone does not discover deleted-template identities.

## Storage preparation and resource limits

The administrative source entry point `ensure_history_index(db)` in [template_history_storage.py](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/template_history_storage.py) prepares the named nonunique `template_history_identity_v1` index on `(workspace_id, identity_digest, revision, _id)`, all ascending, with simple collation. It is not wired to startup or customer requests. Deployment tooling/operator authorization must invoke and verify it explicitly; no production index migration occurred here.

A missing or incompatible named index holds reads with503. Sparse, partial, hidden, unique, prepareUnique or incompatible collation/key definitions are rejected. Any TTL index in this collection holds preparation/readiness. The helper never drops, repairs or changes an existing index or deletes records. Repeated preparation of the compatible index is idempotent. Index metadata is checked before and after each history aggregation; these observations do not lock or globally fence concurrent DDL.

Reads force the named index and simple collation, use a2,000ms aggregation limit and inspect at most1,001 returned wrappers for the existing1,000-record identity cap. Server `$bsonSize` projects full rows only when each is at most4,096 BSON bytes; oversized rows return a small size/null sentinel, including oversized native `_id` values. Client validation requires at most2MiB of accepted BSON, pages at most25 records, and serialized responses at most65,536 UTF8 bytes. Limits hold without truncating malformed records or silently returning a partial accepted history.

The2MiB accepted-history check runs after loading the bounded projected wrappers; it is not a2MiB physical network/server-work cap. A bounded number of wrappers can still contain up to4,096 bytes each. The real-database explain check proves the intended index and one examined document for its owned fixture, not a production performance guarantee. Authority queries, transaction retries, malformed indexed data and other writers need separate operational bounds. Existing mutation history scans and writes retain their earlier limits; the new read path does not retrofit their BSON-byte bounds.

## Lineage and pagination

All retained rows are validated before any page is returned: exact twelve-field checkpoint schema, native scalars, context, deterministic checkpoint IDs, event-specific rules, UTC millisecond timestamp, ordinary-revision uniqueness and exact predecessor hashes. A created revision1 cannot coexist with observed revision0. Observed gaps remain possible and explicitly incomplete. Metadata/graph successors require their retained exact parent. At most one deletion terminal is allowed, at the maximum ordinary revision with the exact same-revision parent hash; orphan or post-terminal ordinary records hold the read.

Ordering is `(revision, terminal-rank, checkpoint_id)`, so a same-revision terminal follows its ordinary parent across page boundaries. The snapshot digest binds ordered full BSON rows, including attribution/time and BSON representation. Cursors are strict canonical base64url JSON of at most768 characters and bind the current actor/UID/workspace/public-and-native identity scope, full history digest, page size and last checkpoint ID. They are unsigned locators, not capabilities or tamper-proof grants.

Every page reauthorizes and revalidates the whole bounded history. Changed context returns403; changed history or a missing cursor position returns409. Empty history without a cursor returns404; a valid original cursor after complete history disappearance returns409. Cursor shape and scope are checked before empty-history handling, preserving422/403. There is no automatic repair, replay or historic snapshot pinning. Concurrency checks show a guarded read can finish before a later edit and its next page then holds as stale.

The thirteen-field envelope exposes context/digests, record count, eight-field audit items, next cursor and terminal presence. `capture_complete`, `content_available`, `restore_available` and `execution_authorized` are always false. Public actors/workspaces/digests remain linkable metadata; Firebase UID is used in a scope hash rather than exposed as a separate response field. Private graph/text/credentials are not returned.

## Verification

Both independent Python/source/test reviews approve the frozen seven Python files. They each independently reran49 pure checks, passing with no skips in0.78s and0.95s; scoped configured medium/high Bandit has no findings. Native controls were independently reviewed, with execution owned by this session.

| Final selected verification | Result |
|---|---|
| Template pure/API selection |417 passed,543 opt-in skips,1 existing warning,6.13s |
| Complete selected template native selection |543 passed,0 skipped,1 existing warning,236.06s |
| Passing identity union |960 distinct selected checks; passing overlap0 |
| New focused overlap |93 passed:49 pure,43 replica-set,1 standalone;0 skipped,1 existing warning,36.31s; all93 already in the960 union |
| Four core modules combined branch coverage |356/368 statements and135/144 branches,95.8984% combined (display96%) |
| Two new history modules |159/163 statements and66/70 branches,96.5665% combined (display97%); storage module100% |
| Other checks |Python compile, scoped medium/high Bandit and diff check pass |

The543 opt-in skips in the pure/API invocation are exactly the separately executed543 native identities, not543 unresolved checks. Counts come from JUnit identities, not summed repeated runs. These are selected template checks and selected core-module coverage, not a fresh whole-application test/coverage claim. Database checks use owned local replica-set/standalone processes and the actual router with a fixture-authenticated user; no live Firebase/provider/AWS integration was tested. Frontend source is unchanged; earlier frontend/browser/build results remain historical and were not rerun here.

Coverage includes actual hinted-index explain, oversized native-ID projection, all session-bound authority observations through member and owner paths, current role/UID/erasure holds, old native identity after replacement, same-revision terminal paging, complete-history removal, stale pages, malformed lineage, count/byte/index-drift/timeout holds, explicit non-destructive index setup, read/edit ordering and unknown commit/standalone behavior. Prior native erasure tests freshly verify purge of checkpoint/terminal history. The root `.coverage` file remains byte-identical to its saved baseline; coverage for this slice is private.

Initial failures remain retained: missing-module pure collection was an unfinished foundation rather than40 failed behavior checks; one native pre-wiring route check returned404 instead of503. The first native run exposed malformed-role pre-handler errors and a missing owner in the closed-workspace fixture, corrected before final checks. The expanded run exposed a test that treated a metadata receipt dict as an HTTP response; the final test checks its actual status/revision/persisted name without weakening the HTTP or stale-cursor assertions. Independent review also led to three red empty-history cursor regressions before the cursor-order correction. An automatic plugin-loading environment failure was rerun with the established explicit async plugin configuration. All final runs above pass.

Evidence is retained under `/tmp/unravler-template-history-ua3wnunk/manifest.json`, including logs/JUnit, coverage, two source-review reports, final document/numerical audit, source hashes, preservation and Desktop/link results. The final manifest includes13 source/document/memory hashes and10 unchanged protected implementations. Of1,821 baseline files,1,813 remain unchanged; the8 intended existing overlaps are three runtime files, four specs/plan documents and session memory. Earlier local work and unrelated files/worktrees are preserved outside those overlaps. Eight Desktop pairs are byte-verified. Owned native fixtures clean up their processes/storage; port4179 is closed and user services are not managed. The bounded foundation is not presented as a full application release.

## Retention, rollout and next work

Retention stays hold-without-eviction: no TTL, automatic purge, archive or content backfill is added. Existing guarded account/workspace erasure continues to purge the collection, including deletion terminals and cap-held history; readers are fenced by erasure authority and cursors cannot restore erased data. The storage schema remains version1 with the participating v2.89 event set. Older validators/writers must still be drained or replaced together; a read cannot establish capture completeness for raw or older writers.

Digest links cannot recover content. This does not add content snapshots, a history UI, immutable/WORM storage, external authentication, rollback protection outside the database backup or restoration. Removing recorded history or rolling back its whole backup can remove evidence. Next, define and implement a bounded content-snapshot contract, including sensitive-field exclusions, byte/cap/retention/erasure rules, before a content viewer and separately reviewed restore workflow. Index preparation/cutover and resource limits still need operational rehearsal. Private sharing/transfer and broader source/filter, sender/team and pilot gates remain separate in the [implementation plan](OUTREACH_DRIPIFY_EIGHT_VIDEO_IMPLEMENTATION_PLAN.md).

Three architecture specs, the implementation plan, this report and eight matching Desktop copies are synchronized before final audit; session memory is written last. No commit, push, deployment, production migration, live-flag change, provider/AWS request, grant or purchase is performed. Headroom tools were unavailable; no token savings are claimed.
