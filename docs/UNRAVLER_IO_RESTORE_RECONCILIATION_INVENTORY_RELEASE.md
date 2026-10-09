# Unravler.io v2.42 — stopped financial and proxy reconciliation inventory

Date: 2026-10-09. Local, uncommitted and undeployed. Earlier changes remain intact.

## Scope and operational contract

Private `python -m outreach.ops.restore_inventory inspect --workspace WORKSPACE --all-writers-and-caches-drained` reports selected financial and managed-proxy metadata under a matching prepared stopped execution epoch. All five action/generation/integration/health flags must remain off; closed workspaces deny. Drain is an operator assertion, not an independently established fleet/cache census. There is no apply, grant or activation command.

The shared suppression guard runs the inspection in a snapshot/majority transaction. Epoch root/journal read fences use that same session, as do projected metadata and global invoice/IP binding lookups. Existing guard/read-fence counters may advance; this is not a strictly write-free operation. Domain receipts, assets, leases, credentials, tokens, uncertainty and budgets remain unchanged. No new journal, schema or index is added. Standalone Mongo denies without a fallback. Final and post-commit checks deny a changed process policy or enabled flag.

The selected collections are outreach_entitlements, outreach_payment_receipts, outreach_access_requests, outreach_proxy_inventory, outreach_proxy_leases, outreach_accounts and outreach_physical_requests. At most 100 rows per collection and 65,536 serialized reviewed metadata bytes are accepted; overflow denies the whole report. Byte limits are checked after reads and are not network/memory allocation bounds. Explicit projections and an additional field allowlist exclude credential/message content; account proxy projection selects only proxy_id. Legacy last_workspace_id proxy rows are candidates, not established current ownership or usable capacity. Lease-to-candidate asset presence does not certify sender ownership.

Receipt checks require original invoice identity, integer seats and native UTC-millisecond term binding. IP checks require a canonical public IPv4, supported provider and nonforeign current owner, with a matching local global binding. Any restore_reuse_blocked field remains a block regardless of value. Missing/malformed bindings and expired/unproven proxy terms are reported. A matching local binding is not authenticated payment, provider ownership or paid resource availability.

The output contains aggregate counts/findings, workspace, execution epoch, timestamp and a deterministic private metadata digest. It never emits raw invoice IDs, IP addresses or credentials. Digests remain linkable and should be kept private. The digest binds this selected snapshot, not later state or a complete external inventory. Every result, including empty inventories and matching guards, explicitly returns activation_allowed=false, completeness_verified=false and provider_ownership_verified=false. Financial facts, provider resources and source completeness always require external review.

## Verification

33 focused checks pass: 24 unit/CLI and nine native Mongo cases, including an actual concurrent insert between collection reads which remains outside the same-session snapshot, default naive-BSON invoice/IP match/block/mismatch, metadata projection, retained unknown outcomes, candidate scope, capacity/closed/root/post-commit denial and actual standalone rejection. Focused run: 11.14s, one existing multipart warning. New modules have 98% combined statement coverage (core98%, CLI97%). Independent Python review approved the bounded scope; its recommended native binding check was added and passes. Compile, scoped Bandit and whitespace checks pass.

512 restore regression checks pass (103.26s, one existing warning), with two opt-in physical-backup drills skipped. Two subsequently added native checks also pass in the final33-case focused run: 514 distinct passing checks across these runs. No fresh full-backend or physical-backup result is claimed.

Owned replica PID95540, matching owner manifests and private storage were cleaned after confirming only admin/config/local databases remained. Ports27028/27029/6389 are closed; user Mongo PID1735 remains unchanged; no Redis was started. All27 prior frozen source/test/cache fingerprints remain unchanged;31 final fingerprints match. The three specs, runbook and report byte-match Desktop copies;146 spec links/41 release reports and eight protected backup copies verify.

## Remaining work

This does not reconcile missing provider operations or every financial authority, authenticate or establish completeness of outside-backup sources, establish unproven reply evidence, rotate shared credentials, verify real deployment identity/IAM/kernel egress or run production recovery/pilot checks. Current-source/provider reconciliation and explicit new-epoch activation design/drills remain separate. No provider material is opened and no real provider/AWS call or purchase occurs. No commit, push, deployment, grant or flag enablement. Frontend unchanged; previous frontend tests/build remain historical.
