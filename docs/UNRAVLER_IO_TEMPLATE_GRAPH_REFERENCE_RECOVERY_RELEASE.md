# Unravler.io v2.84 — Same-tab template sequence-update recovery

Updated: 2026-10-18 IST. Frontend-only local implementation against HEAD `e63bcfe`, preserving approved uncommitted [v2.83 metadata recovery](UNRAVLER_IO_TEMPLATE_METADATA_REFERENCE_RECOVERY_RELEASE.md) and unrelated files. The earlier [frontend/backend deployment](UNRAVLER_IO_V2_82_DEPLOYMENT.md) is separate; this slice is uncommitted and undeployed.

## Behavior and bounds

The graph editor now writes and verifies its original locator before one POST. After reload or route remount, Templates offers **Check saved sequence update status**. It fetches a fresh current-account/workspace context and then the matching original UUID/input status. It does not replay graph content, create a replacement UUID, infer confirmation from current template resemblance, or substitute later catalog content for the original result.

The independent `unravler.outreach.templateGraphReferences.v1` sessionStorage envelope retains only contract version, workspace ID, original operation scope digest, canonical UUID and exact input digest. Each operation namespace permits at most ten locators and8,192 UTF-16 code units without eviction. No graph, node/configuration/text, original review proof, template ID, token or separate Firebase UID is persisted. Hashes and workspace identifiers remain linkable metadata.

Creation storage is unchanged. Metadata and graph storage keep distinct keys, endpoint namespaces and receipt validators. The common bounded store and recovery hook were extracted from v2.83 without changing its public wrapper contracts; the full metadata suite remains applicable. Either restored hold disables Use, details editing, sequence editing and deletion, with synchronous per-handler guards against references arriving after render.

## Confirmation and failure handling

Recovery requires current token/view/mount, exact HTTP200, matching locator/input, strict fourteen-field historical receipt, custom-template identity, safe integer revision increment and original/native/review/result/graph digests. The current-authority backend remains responsible for authenticating and authorizing its historical assertion; reload recovery cannot reconstruct the lost original graph proof. The live editor retains its stricter in-memory original proof comparison. Confirmation reloads current templates and preserves later replacements.

Verified conditional cleanup and reread cannot discard newer same-scope requests. Missing retained references are restored before another context unlocks; newer stored UUIDs are preserved and explicitly recoverable. Foreign locators remain without foreign original-status disclosure. Blocked/corrupt/full/unverifiable storage, stale credentials, mismatched receipts, network errors and missing404 remain held.

Writing a locator and crashing before POST can leave an indefinite404 hold. There is no cancellation/tombstone protocol, automatic retry, eviction or fresh-UUID bypass. Tab/browser/storage loss, raw scripts and cross-tab coordination remain limits. Only the locator survives; unsaved graph drafts and immutable revision history are not supplied by this change.

## Verification and provenance

Test-first failure is recorded in `/tmp/unravler-graph-reference-ZUPJji/red.log`. The initial shared extraction passed603 frontend tests and48 compiled synthetic browser journeys; the production build caught a missing React effect dependency. A stable useCallback initializer and complete dependency list corrected it without suppressing the rule. Final-source results:603 frontend tests across57 suites, zero skipped/failed,25.361s;48 compiled synthetic browser journeys,55.8s; production build78.42s with existing dependency/source-map/Tailwind/bundle warnings. The172 affected checks across8 graph/metadata suites overlap the full frontend run;40 checks and2 browser journeys are new over v2.83. Earlier runs remain historical.

Selected shared/new-hook/store/receipt coverage is153/161 statements95.03%,110/111 executable start lines99.10%,98/107 branch arms91.59%. Scoped hook/unused-variable lint and whitespace checks pass; final production build also enforces effect dependencies. Independent source/test review approves:136 focused checks were independently rerun, followed by42 gallery checks after the dependency fix. Verification logs and the baseline/preservation manifest are retained in the evidence directory. Independent evidence/document review follows the final frozen manifest before memory is written.

The unchanged graph policy/receipt backend contracts pass87 checks with one existing warning in2.17s. Backend source/schema/collections/authority/erasure behavior is unchanged; full backend/native suites were not freshly rerun. Browser journeys use actual compiled components with synthetic APIs/authentication and do not establish real login, provider or production fidelity.

## Remaining work

Next: same-tab persistent deletion locators, then sharing/ownership requirements and immutable template revision history. Deletion references still remain view-memory-only. Broader source/recipient fidelity, team/sender governance, security/legacy migration, authenticated restore/reconciliation/reactivation, controlled integration/health/IAM-egress checks and an actual pilot remain open.

No commit, push, deployment, production migration, live flag change, provider/AWS request, grant or purchase occurred. Architecture specifications, roadmap and Desktop copies are synchronized after verification; session memory is updated last.
