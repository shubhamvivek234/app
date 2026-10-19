# Template snapshot mutation integration: usage-stop checkpoint

Resumed manually after the allowance reset on 2026-10-19 IST. The local v2.93 implementation and final verification are recorded in the [release report](UNRAVLER_IO_TEMPLATE_SNAPSHOT_MUTATION_INTEGRATION_RELEASE.md); this earlier planning checkpoint is historical. The single continuation automation is paused. Do not restart already completed source work from the older schedule below.

2026-10-19 IST. Planning only: no application source or tests changed in this continuation. The account reached the user's cutoff of 98% used / 2% remaining before implementation began. Actual short-term reset: 2026-10-19T15:31:53Z (9:01:53 p.m. IST). The existing one-shot heartbeat `continue-unravler-revision-checkpoints` was updated successfully to continue at 2026-10-19T15:33:00Z (9:03 p.m. IST), then pause after its run.

## Current verified local baseline

Local HEAD is `c9fadf7a6317ef5b76a849a6da71de5004a54e01`, following v2.92 source commit `230f39b`, native-gallery fixture correction `3b21bd0`, and the deployment record. The prior deployment is recorded in AGENTS.md; this planning turn did not recheck production or hosted CI. Existing dirty worktrees, `.gitignore`, the REA skill and the two untracked Prosp documents were observed and left untouched. No source/test/service/coverage changes or tests ran. Headroom tools are unavailable; no token savings are claimed.

Read the [v2.92 report](UNRAVLER_IO_TEMPLATE_GRAPH_SNAPSHOTS_RELEASE.md), [roadmap](OUTREACH_DRIPIFY_EIGHT_VIDEO_IMPLEMENTATION_PLAN.md) and the three current architecture specifications before implementation. Earlier reports describe their dated local validation; do not treat their historical HEAD or no-deployment statements as the current deployment state.

## What the source inspection establishes

- `outreach/core/template_snapshot_capture.py` owns `capture_reviewed`'s transaction. The explicit metadata/graph wrappers each invoke a separate transaction. Calling those wrappers inside a template mutation would not implement one atomic cross-kind capture.
- Both codecs already expose source-bound sealing and strict private decryption, separate identity/scope domains, and bounded retained-row loaders. Metadata permits 1,000 retained rows; graph permits 100. Each has an 8MiB accepted-BSON cap with separately documented loading limits. No eviction or repair exists.
- Creation checkpoints are appended in both `template_governance.create_template` and `template_saves.save_template`. Shared metadata and graph replacements append checkpoints from `template_metadata._replace_metadata` and `template_graphs._replace_graph`. The shared reviewed deletion helper appends its baseline/terminal after literal deletion and native absence. Recoverable receipt precedence must remain intact.
- Existing snapshot capture requires prepared snapshot/history indexes, current unique UID/user/workspace authority, the caller's owning session and matching full-BSON checkpoint lineage. New integration must not silently turn missing production indexes or keys into an undocumented rollout prerequisite for existing authoring.

## Resume work

1. Recheck usage, HEAD, applicable instructions and current dirty files. Preserve all unrelated files, user services/worktrees and root `.coverage`; keep evidence private. Do not redo completed v2.92 source work.
2. Define a bounded coherent integration contract before wiring: explicit storage/key/cutover prerequisites; trusted configuration or admission policy if required; exact before/after revision capture for creation and edits; pre-delete content versus same-revision deletion terminal; metadata/graph atomicity, shared transaction resource bounds and capacity failures. These rollout choices remain unresolved; this checkpoint approves no new flag or production change.
3. Implement within the caller-owned guarded transaction using an internal in-session path, without nested owning wrappers or request-selected storage callbacks. Preserve current authority checks and historical receipt-first recovery. An old completed receipt must not replay a mutation, backfill snapshots or require newly introduced storage/key prerequisites merely to confirm its original result.
4. Verify both legacy and recoverable paths, unchanged public contracts, exact native/full-record binding, baseline/result consistency, immutable repeated capture, both-kind rollback on failure, missing/conflicting/TTL indexes and keys, cross-kind capacity, final revision, malformed legacy content, unknown commit result, erasure after source deletion, standalone denial and relevant concurrent edit/delete/role/erasure races. Use meaningful regressions and actual owned database checks; do not weaken the gallery identity contract.
5. Follow applicable independent review instructions and resolve findings before completion. Update the release report, three architecture specifications, roadmap and matching Desktop copies with actual verified scope/counts/limits; update AGENTS.md last under 80 lines. Do not assert complete history or enable content/restore/completeness flags before their later contracts exist.

All new work remains local. No commit/push/deploy, production migration, live action/config change, provider/AWS request, grant or purchase is authorized by the scheduled continuation. The next authorized user deployment request can be handled separately.
