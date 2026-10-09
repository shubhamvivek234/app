# Unravler.io v2.36 — selected restore deletion exclusions

Date: 2026-10-09. Local, uncommitted and undeployed. Foundations through v2.22 remain at `04ca28b5d1dd7bd213ea67e951970e19fd93bdf3`; all earlier local work remains intact.

## Result and scope

The private controller can restore selected, independently retained deletion denies into an older database. It installs missing global Firebase identity digest tombstones and a target workspace stop in one snapshot/majority transaction. This closes the selected auth/tenant recreation gap without activating outreach, purging restored data, fabricating ownership or claiming that deletion completed.

Successful import means the selected negative facts are present. It does not prove source authenticity, completeness, a relationship between the selected global identities and workspace ownership, all-user/whole-product deletion, reply/DNC recovery, financial reconciliation, production restoration, or readiness to activate. A SHA-256 digest checks the exact input bytes; the operator must establish origin and retain the artifact outside the database/configuration backup. These files contain stable pseudonymous identity hashes and deletion times and require private handling.

## Source export and bounded input

`outreach.core.restore_exclusions.export_manifest` reads one already-closed workspace guard and 1–100 explicitly selected, already-retained identity tombstones with majority read concern. It denies absent selections, duplicates, unsupported original deletion state or nonnative/unproven times. Reads establish individual retained negative facts, not one atomic source snapshot or a complete deletion inventory.

The manifest contains exactly version 1, the target's canonical workspace-guard digest, original `stopped|purging|erased` state, original UTC millisecond request time and selected identity digest/request-time pairs. It includes no UID, email, owner, cookie, provider key, recipient, credential or outcome payload. This is an internal manifest format, not a provider attestation.

Import bounds the source to 65,536 bytes before parsing and 100 distinct identity hashes. Unknown fields, duplicate JSON keys/IDs, nonfinite values, malformed UTF-8, boolean versions, noncanonical dates, unsupported state and future/unproven dates deny. Parsed facts are immutable. The exact raw byte digest, selected-set digest and original-facts digest bind the review and permanent journal.

The CLI export writes an exclusive 0600 regular file in an owned private directory; it never overwrites. Partial failure removes only its own inode and preserves replacements. Input accepts bounded stdin or an owned private regular file with no symlink/hardlink; metadata changes during read deny. CLI results contain counts/digests, never the manifest or identity list. Runtime and argument failures are sanitized.

## Stopped import and recovery

Import requires the v2.35 matching prepared stopped epoch, all five execution/health flags exactly false, an identified all-writer/cache drain assertion and exact source/evidence/inspection/operator review. The existing shared erasure control acquires the workspace guard and uses snapshot/majority. `AuthorityDatabase` fences the exact epoch root/journal and guard. Global identity reads/upserts explicitly use the same transaction session with their canonical digest identity; they intentionally have no tenant filter.

Missing identity tombstones receive the original native request time through `$setOnInsert`. Existing identity dates and fields remain untouched. A workspace without an erasure stop receives only `erasure_state=restore_excluded` and the original request time. Stronger or unknown existing closures, request records and completion timestamps remain intact apart from ordinary guard/fence metadata. No erasure request, owner, `erased` status or completion timestamp is manufactured. Credentials, consent, provider assets, leases, physical ownership/tokens, budgets and uncertain/received work remain as held by the stopped epoch.

Selected facts are read back before the metadata-only unique journal is saved. Captured epoch policy and flags are checked after the final awaited journal write; an observed mismatch rolls the whole transaction back. Commit can follow the last local check. The drain remains an assertion; raw/older writers and independently cached auth decisions remain outside the protocol.

Concurrent and saved retries retain one source journal. Exact saved evidence must match, and the current root, workspace exclusion and all selected identity tombstones must still be present; an old receipt cannot fabricate a missing exclusion. A real-database commit-then-raise test simulates acknowledgement loss and verifies recovery without reinstalling over later metadata. This is not SIGKILL, broker redelivery or real-driver unknown-commit evidence. Actual standalone Mongo denies before import, with no fallback.

Evidence TTL removal for the journal, global identity tombstones and workspace guards precedes strict index builds. A unique `(workspace_id, execution_epoch, source_digest)` index enforces source history. Erasure classifies the journal and retains only hashed provenance; global identity tombstones and workspace denial guards retain their existing permanent purpose. This release never runs purge or removes an exclusion.

## Private procedure

On the trusted source, select actual retained identity digest references and an already-closed workspace. Export with `python -m outreach.ops.restore_exclusions export --workspace WORKSPACE --identity-digest DIGEST --output-file PRIVATE_FILE`; repeat the identity option for further selected facts. The output directory must be owned and private. Keep the artifact and independently established provenance outside backups; the app cannot verify that storage location.

On the isolated restored target, keep every writer/cache drained and the five flags disabled. For a target whose deletion guard was lost, prepare the stopped v2.35 epoch first. Normal preparation rejects an already-closed workspace; do not bypass that closure to create a missing root. Such a closed target without a valid matching root needs separate recovery design and remains unavailable to this importer.

Run `python -m outreach.ops.restore_exclusions inspect --workspace WORKSPACE --manifest-file PRIVATE_FILE` (or `--manifest-stdin`). Review counts and the exact digest. Apply with `apply`, the same source, `--operator`, `--source-digest`, `--evidence-digest`, `--review-digest` and `--all-writers-and-caches-drained`. Retain the original command digests for acknowledgement-loss retries. No cookie, key, UID, activation, grant or replay arguments are accepted. Keep provider work stopped after successful import.

## Verification

The final full run passes 2,657 backend tests (2,637 outreach plus 20 account/auth), with 44 historical opt-in skips and two existing warnings, in 718.44 seconds. All 63 new checks pass: 28 core unit cases, 20 CLI/file cases and 15 actual Mongo cases including standalone denial (13.58 seconds). Focused statement coverage is 95% combined (core 95%, CLI 96%). The 181-case erasure/restore/mailbox-lifecycle/account/auth affected run passes (113.61 seconds). Independent source/security/test-contract review approves; the reviewer independently passed all 48 unit/CLI cases. Compilation, scoped Bandit medium/high checks, both Compose configurations and whitespace checks pass. Frontend tests/build were not rerun for this backend-only change.

The final database audit found only admin/config/local and zero temporary databases. The exact PID 52515, command and matching ownership manifests were verified before stopping the owned replica, removing its storage and final test directory. Ports 27028/27029/6389 are closed; the original user Mongo process was preserved and no Redis was started. Tested source fingerprints, the existing repository coverage file and HEAD remain unchanged. Private logs and cleanup receipts retain the evidence. Independent final review also verified the logs, five synchronized documents, 35 linked reports, 128 specification links, eight protected backup copies, all nine fingerprints and cleanup evidence without discrepancies.

Initial fake guard/options and cross-module fixture setup were corrected. One initial standalone fixture exceeded Mongo's native database-name limit; the name was shortened and teardown moved into a nested `finally`. Its exact process was confirmed absent, port closed and owned storage removed. That failure is retained in the local logs and cleanup receipt; no application fallback, weakened timeout or excluded failure was introduced.

Frontend code is unchanged; prior 99 frontend/build results remain historical. No production source was exported/imported, real credentials opened, provider/AWS call made, purchase or grant issued, flag enabled, commit created/pushed or deployment performed. Repository coverage and earlier unrelated dirty files are preserved. Pre-edit eight-copy backup: `/tmp/unravler-docs-before-v2-36-20261009`.

Next: independently retained suppression/reply/financial/provider reconciliation and completeness evidence, explicit new-epoch activation design and isolated restore/IAM/egress drills. Selected deletion exclusions alone never authorize activation.
