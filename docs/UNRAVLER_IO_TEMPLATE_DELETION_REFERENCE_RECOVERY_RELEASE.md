# Unravler.io v2.85 — Same-tab template-deletion recovery

Updated: 2026-10-19 IST. Frontend-only local implementation against HEAD `e63bcfe`, preserving approved uncommitted [v2.83 details recovery](UNRAVLER_IO_TEMPLATE_METADATA_REFERENCE_RECOVERY_RELEASE.md), [v2.84 sequence recovery](UNRAVLER_IO_TEMPLATE_GRAPH_REFERENCE_RECOVERY_RELEASE.md) and unrelated files. The prior [frontend/backend rollout](UNRAVLER_IO_V2_82_DEPLOYMENT.md) is separate. This slice is uncommitted and undeployed.

## Behavior and bounds

Before sending a reviewed deletion POST, Templates writes and verifies an original-request locator. After reload or route remount, **Check saved deletion status** explicitly obtains fresh current-account/workspace context, then requests only the matching original UUID/input status. No deletion is replayed, and current absence or resemblance cannot prove the historical result. Confirmation reloads the current catalog and preserves a replacement template.

The independent `unravler.outreach.templateDeletionReferences.v1` sessionStorage envelope contains only contract version, workspace ID, original operation scope digest, canonical UUID and exact input digest. Each operation namespace permits at most ten locators and8,192 UTF-16 code units, without eviction. Names, descriptions, graphs, template IDs, original native/review proof, tokens and separate Firebase UIDs are not stored. Workspace IDs and digests remain linkable metadata.

Creation storage is unchanged. Details, sequence and deletion recovery use independent storage keys, endpoint contracts and receipt validators. The shared store/recovery hook retains the earlier update defaults; its deletion configuration supplies the deletion-specific wording and validator. Any restored hold blocks gallery Use, details editing, sequence editing and deletion, with synchronous handler checks for locators arriving after render. Existing backend role/UID/erasure authority and transaction behavior are unchanged.

## Confirmation and failure handling

Restored confirmation requires current token/view/mount, exact HTTP200, an exact eleven-field historical deletion receipt matching the locator, custom-template identity, a nonnegative JS-safe revision and all three native/review/scope digests. Deletion may confirm the final safe revision because it needs no revision increment. The authenticated backend supplies the historical assertion; a reloaded browser cannot reconstruct the lost original native proof. The live in-memory operation retains its stricter original-proof matcher.

Conditional cleanup and reread preserve a newer same-scope request. Internal departure from a held live operation restores its locator only when that scope is absent; it preserves a newer stored request and lets reentry adopt it for explicit status inspection. Corrupt or unavailable storage prevents discarding that live hold. Foreign references remain without a foreign original-status request. Storage/write/readback/cleanup failures, malformed or non200 receipts, credential changes, network errors and missing404 retain the hold.

A crash after locator persistence but before POST can leave an indefinite404 hold. There is no cancellation/tombstone protocol, automatic replay, eviction or fresh-UUID bypass. Tab/browser/storage loss, raw scripts and cross-tab coordination remain limits. Internal departure is guarded; arbitrary route unmount cannot restore already-lost storage. Only locators survive; this change provides no durable template revision history or browser-wide recovery guarantee.

## Verification and provenance

Evidence and preservation baseline: `/tmp/unravler-deletion-reference-UG4v70`. The initial missing-module/test-first failure is in `red.log`. Independent review found that stale live operation A could prevent departure when newer stored B existed. The regression failed before the departure fix (`review-red.log`); final recovery preserves B, leaves/reenters and checks B while keeping a replacement's native proof. A fixture correction restored the current replacement catalog rather than removing the enabled-row assertion.

Final frontend suite:657 passing checks across58 suites, zero skips/failures,9.388s. This adds54 cases over the preserved603-case v2.84 run, with no removed cases; duplicate parameterized names are disambiguated by occurrence in `test-delta.json`. The104 focused deletion checks and203 affected checks across7 recovery/storage suites overlap the full suite. Selected deletion/shared-hook/store/receipt coverage is153/160 statements95.62%,110/111 executable lines99.09%,111/119 branch arms93.27% and33/34 functions97.05%. New deletion hook/store/historical validator each have100% selected coverage. This is not whole-page/application coverage.

All50 compiled synthetic browser journeys pass in48.4s, including two new reload/404 journeys. The earlier missing-status browser case now waits for the actual GET and enabled status control before asserting. APIs and authentication are synthetic; these journeys do not establish real login, provider or production fidelity. Production build passes in97.04s with existing dependency/source-map/Tailwind/bundle warnings; scoped hook/unused-variable lint and whitespace checks pass.

The full suite exposed an existing wizard test reading a save before native WebCrypto completed after a fixed20ms delay. A test-only wrapper now awaits the genuine digest promises, retains native UUIDs and preserves every assertion. Independent source/test review approves the bounded source changes and reran104 deletion checks plus32 wizard checks successfully. Initial exploratory runner/path errors and an unrelated timeout under concurrent load are retained in the logs; only the final successful runs above establish completion.

The unchanged deletion/governance backend contracts pass73 checks, zero skips, one existing multipart warning,10.75s, using an explicit async test plugin with third-party autoload disabled. Backend source, schema, collections, authority and erasure behavior are unchanged. Full backend/native suites were not freshly rerun; earlier native evidence remains historical. Browser service4179 is stopped after verification.

The frozen manifest records final source/test/document hashes, all1,799 baseline file comparisons, Desktop copies and local document links. Final independent evidence/document review follows the manifest before session memory is written last. Earlier local release files outside the intentional shared-hook/gallery/test/document overlaps remain intact.

## Remaining work

Next: establish template sharing/ownership requirements, then immutable template revision history. Bounded same-tab locators now cover creation, details updates, sequence updates and deletion. Missing receipts and tab/storage loss remain explicit limits. Broader source/recipient fidelity, team/sender governance, security/legacy migrations, authenticated restore/reconciliation/reactivation, controlled integration/health/IAM-egress verification and an actual pilot remain open.

No commit, push, deployment, production migration, live flag change, provider/AWS request, grant or purchase occurred. The three architecture specifications, roadmap and matching Desktop copies are synchronized after verification; session memory is updated last.
