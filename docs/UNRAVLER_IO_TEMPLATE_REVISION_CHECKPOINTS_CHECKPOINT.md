# v2.87 metadata revision checkpoints — continuation checkpoint

Continuation record, 2026-10-19 IST: the [bounded foundation report](UNRAVLER_IO_TEMPLATE_REVISION_CHECKPOINTS_RELEASE.md) supersedes the unfinished-documentation status below. This document retains the original pause state and resume instructions as historical provenance. Final source/document hashes and preservation evidence are recorded in the final manifest alongside the historical checkpoint manifest.

2026-10-19 IST. Implementation and final source reviews are complete; documentation synchronization and final evidence/document audit are unfinished. Do not describe this as complete template revision history or a completed release. Keep local; no commit, push, deployment, production migration, live flags, real provider/AWS calls, grants or purchases.

Workspace: `/Users/shubham/Documents/Workspace/SocialEntangler/app`. HEAD remains `e63bcfef3293eff407211096e764e4f516e3642b`. Evidence: `/tmp/unravler-template-revision-checkpoints-jg1s25il`, baseline1,810 hashes and exact `root-coverage-before`. Preserve all approved local v2.83–v2.86 and unrelated files/worktrees. No Headroom integration was available.

## Implemented bounded scope

`outreach/core/template_revision_checkpoints.py` appends reference-only twelve-field records to `outreach_template_revisions` inside the existing authorized metadata replacement transaction. Observed baselines do not prove creation. Metadata results link original revision/hash; native identity separates replacements. No content, credentials or Firebase UID is copied. `_replace_metadata` calls it after exact BSON replacement readback and before recoverable receipt insertion. Legacy and recoverable metadata edits share the helper; historical receipt replay returns before it. Normal erasure includes the new collection.

Final review fixes require an active transaction, strict context types, identity-wide inspection independent of redundant template IDs/numeric Mongo predicates, complete declared-parent/hash validation, and a1,000-checkpoint per-identity cap including new entries. Corrupt/future/missing-parent/mismatched records and overflow hold without repair/eviction. Only absent baseline/result records are inserted; existing records are preserved. All template/receipt/checkpoint/authority writes roll back together.

Application-protocol append-only behavior is not WORM, authentication, outside-backup protection or complete history. Graph/create/delete checkpoint capture, immutable content snapshots, viewer/restore and public/private/external sharing are not implemented. Query output is capped after reading; scanned work/BSON bytes are not bounded and no compound index exists yet. Rollout must replace/drain older metadata writers; gaps remain explicitly observed rather than invented.

## Final verified evidence

- `backend-final.log/.xml`:328 passes,62 historical opt-in erasure skips,1 existing warning,2.80s. Includes27 new pure cases; no full application claim.
- `native-final.log/.xml`:122 passes,0 skips,1 existing warning,48.20s:20 new checkpoint cases+51 metadata+51 recoverable updates. Owned Mongo fixtures stopped normally.
- `coverage-final.log`, `final-coverage.json`:47 overlapping focused checks=27pure+20native,0skip,12.58s;75/78 statements96.15%,39/42 branches92.86%,95% combined.
- Python compile, scoped medium/high Bandit (`bandit-final.log`) and diff checks pass.
- Both independent source/test reviews approve final code. `independent-checkpoints-final.log/.xml`:27pure pass; `reviewer-source-report.json` records another independent27pure and final five source/test hashes. Earlier24/117 evidence is historical; `review-red.log` records seven failures before fixes.
- Frontend source is unchanged. Prior v2.86 evidence680frontend/53browser/build70.29s remains historical; no fresh frontend/build claim. Root `.coverage` matches the saved backup. User services/worktrees remain untouched.

## Resume plan

1. Read current AGENTS.md, three architecture specs and this checkpoint. Check actual short-term usage first; at<=2% schedule once after its actual reset and stop implementation.
2. Verify baseline/source hashes and final reviewed source; do not redo finished implementation or weaken tests. Consider only concrete review findings if any new evidence arises.
3. Write `docs/UNRAVLER_IO_TEMPLATE_REVISION_CHECKPOINTS_RELEASE.md` as a bounded foundation report with the exact scope/counts/limits above. Update the three specs to v2.87 and the roadmap, keeping full history explicitly unfinished. Next bounded work: creation/graph capture, then content snapshot/read/view contracts; no restore/activation shortcut.
4. Synchronize three same-named specs plus DOC_1/2/3 aliases, roadmap and report into `/Users/shubham/Desktop/Unravler/Unravler.io Docs/` (eight pairs). Freeze final hashes, baseline differences, links and proof; independently review final evidence/docs using existing `/root/search_trust_review` if available, otherwise follow project review rules.
5. Update AGENTS.md last, preserving history and keeping79 lines. Only then report bounded completion. No production or Git actions.
