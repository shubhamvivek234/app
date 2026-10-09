# Unravler.io v2.41 — isolated physical backup and rollback rehearsal

Date: 2026-10-09. Local, uncommitted and undeployed. This change adds a regression harness, not application behavior, schemas or activation. Foundations through v2.22 remain at `04ca28b5d1dd7bd213ea67e951970e19fd93bdf3`; all earlier local changes remain intact.

## Verified scope

The five selected restore mechanisms now have a combined physical backup/restore rehearsal. The harness uses actual `mongodump` and `mongorestore` 100.14.1 against a disposable single-node replica set on fixed loopback port 27028. It creates only randomly named synthetic source/target databases. No production URI, database name, input archive or real provider material can be supplied.

Two cases cover an archive without an execution root and an archive containing a root prepared under an older execution identity. Each case makes one gzip archive, then restores it twice into its generated target. Both restoration cycles prove that post-backup selected negatives and import journals are missing, the retained new process epoch prevents positive admission, and reviewed reimports recover the blocks without activating anything. The second cycle is an actual second rollback: it removes the newly installed roots, negative facts and journals and still requires preparation and reconciliation again. Across the two cases this is two physical dumps and four physical restores, with 20 fresh exclusion applications and 20 saved receipt retries.

The archive is created before the later synthetic source facts. Separate private files retain the five reviewed manifests outside that particular database archive. Existing export/private-file/import APIs are used for deletion identity/workspace closure, DNC/email suppression, sender-specific LinkedIn reply stops, invoice reuse blocks and physical-IP reuse blocks. Files are exclusive 0600 in a 0700 directory. The archive is also private, and its byte digest remains unchanged through both restores. Deterministic identity/IP hashes remain linkable; these artifacts are not anonymous.

This provides local physical database rollback evidence beyond individually seeded older-target fixtures. It does not prove a production or Atlas snapshot restore, authenticated/complete source facts, externally protected deployment identity, fleet/cache drain, oplog consistency, multi-database recovery, provider behavior, IAM or kernel egress. Source writes are quiescent during the synthetic dump; the harness does not establish online-backup consistency. The separate files are outside this archive, not proven outside all filesystem or cloud backups. The new execution anchor is retained in the test process through monkeypatching, not installed in real deployment configuration.

## Restore replacement and retained evidence

MongoDB `--drop` alone leaves collections absent from an archive intact. The harness explicitly drops only its generated target database before namespace-remapped restoration. This models replacement of an older database, rather than accidentally retaining newer exclusion collections. Source and target names are bounded below 64 characters, generated internally and checked absent before ownership is established. Cleanup drops only those proven-owned names and always closes the client. No existing user database is deleted; no running user Mongo service is stopped.

After each physical restore, the harness checks original unique account-index metadata, missing post-backup negatives/journals and missing or stale epoch admission. It prepares a new stopped root for the active and separately deleted workspace, then applies and retries all five sources. Deletion denies workspace/identity recreation without closing an unrelated workspace. DNC aliases, suppressed email and sender-specific reply preflight deny; another sender remains unaffected. The original invoice reservation is created through the real binding helper, and identical invoice/workspace/seats/UTC term reuse with `reject_restore_blocked=true` denies specifically because of the restored block. Physical-IP negative admission denies too.

The test checks held execution status, exact owner/token, latched permission and revision advancement. It preserves synthetic encrypted credentials, proxy inventory/lease, physical uncertainty, manual unknown-outcome receipt/owner, request budgets, revoked entitlement and original payment receipt. Existing authority fence counters may advance; semantic evidence remains intact. Known never-submitted manual work stays cancelled and campaigns paused. It creates no inbox history or reply events. Positive epoch admission and an explicit permission-grant attempt continue to deny after all reimports. No HTTP factory, actual provider transport or key-service boundary is exercised by this new harness; those earlier local checks are separate evidence.

## Reproducible local procedure

Use an independently owned disposable replica set named `unravler-test` bound to `127.0.0.1:27028`; do not reuse application data. Install the MongoDB backup tools locally. The drill checks the replica name, fixed loopback URI and generated database ownership. All five execution/health flags and epoch values are scoped to the test process, with no production configuration edit.

Run from the repository:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OUTREACH_TEST_LOCAL_MONGO=1 OUTREACH_TEST_PHYSICAL_BACKUP=1 \
  .venv/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_outreach_restore_backup_drill.py -q
```

Both opt-ins are required. Without them the physical cases are skipped; when explicitly requested, missing backup binaries fail rather than silently bypassing the drill. Fixed argument arrays invoke local tools without a shell, capture their output and bound each subprocess to 30 seconds. The fixture cleans generated databases; owned test artifacts and the independently owned disposable server should be removed after verification. The procedure supplies no production restore or activation command.

## Verification and review

The final targeted run passes **525 checks** in **128.22 seconds**, with one existing multipart warning. It covers every restore test module, the new physical cases, real execution ownership cases, paid lifecycle and account/auth companions. The final focused physical run passes both cases in 8.28 seconds. Independent Python safety/proof review approved the final harness and independently passed both cases in 7.28 seconds. The reviewer verified namespace safety, generated-target replacement, two rollback cycles, exact invoice binding, stopped owner/latch/token evidence and all selected negative gates. Independent draft-document audit approved the scope, counts and operational limits. No HIGH/CRITICAL findings remain. Compilation, scoped Bandit medium/high and whitespace checks pass. No new runtime code was introduced, so fresh frontend/build or deployment-configuration validation is not claimed. Optional format/type tools remain unavailable.

An initial run failed because generated names exceeded MongoDB's 63-character limit; the prefix was shortened and an explicit bound added. Another run exposed an assertion that compared the intentional dispatch authority counter as immutable evidence; the final comparison ignores only that existing counter while retaining all semantic fields. Cleanup now establishes ownership only after replica/nonexistence checks. Reviewer suggestions strengthened exact invoice reuse and held owner/status/latch assertions. No application guard, shared fixture, timeout, test selection or production fallback was weakened.

Application code, runtime configuration, indexes and frontend remain unchanged in this slice. The previous complete 3,004-backend-test run belongs to v2.40 and is historical; this release reports its own targeted results separately. No production source export/import, real credential opening, AWS/provider call, purchase, grant, flag change, commit, push or deployment occurs.

Final cleanup verified exact owned PID 91825, command and both ownership manifests; only admin/config/local and zero temporary databases remained. The owned replica, storage and both primary test directories were removed; ports27028/27029/6389 are closed and user Mongo PID1735 is unchanged. No Redis was started. All27 frozen source/test/cache fingerprints match; the26 earlier runtime/test/cache files, original .coverage and HEAD remain unchanged. Session memory was untouched until its final update. Independent reviewer artifacts are removed from that review's exact owned pytest directory separately; unrelated pytest paths are preserved. Private logs and ownership/cleanup/preservation receipts remain under `/tmp/unravler-v241-*`.

The three architecture specs, operator runbook and this report match Desktop copies; all143 local architecture links resolve and40 linked release reports byte-match. Earlier document content is preserved outside the version/current-summary update and appended slice. The eight-copy pre-edit backup is `/tmp/unravler-docs-before-v2-41-20261009` (directory0700/files0600). Final sync/preservation/cleanup checks are local, supplementing the independent source/execution/draft-contract reviews.

Next: remaining provider/resource and financial facts/completeness, unproven reply evidence, explicit new-epoch activation design and genuine isolated deployment/IAM/egress/pilot checks. Selected negative reconciliation and this synthetic rehearsal cannot authorize activation.
