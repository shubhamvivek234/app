# Unravler.io restore-helper reverification — v2.51–v2.54

Date: 2026-10-10. Scope: the three local offline restore helpers and their tests, with regression checks against the existing restore protections through v2.50. This review does not certify the full application or a production deployment.

## Outcome and corrected claims

Reverification reproduced material correctness problems in the earlier helpers. Those problems have been corrected locally. The earlier descriptions of completed authenticated reconciliation, a transactional activation rehearsal and verified reply recovery were too strong and are withdrawn.

These modules have no API, worker or dispatch call sites. They compare or validate caller-supplied metadata. They do not read or mutate production authorities, resolve uncertain provider operations, restore reply suppressions or activate an execution epoch. The existing `restore_epoch.positive` denial gate is unchanged.

## Findings and repairs

1. **Independent comparison and false completeness.** The signed helper accepted a separate local metadata argument but did not use it; the underlying verifier compared summaries against metadata inside the same artifact. A self-consistent artifact could therefore hide divergence and claim completeness. Both paths now require and compare a separate caller-supplied view. Matching selected records reports only `selected_metadata_matches`; `completeness_verified` remains false even for matching empty groups. Independent database origin/currentness and coverage are still unproven.
2. **Schema and resource bounds.** Versions/counts now require integers rather than booleans. Exact schemas, unique source/record identifiers, all three source groups, digest formats and bounded references are checked. Artifacts/views accept at most 100 selected rows per group, 12 source descriptors, eight levels of JSON nesting and a conservative 64KiB bound per supplied value. Unknown fields, opaque values, cycles and oversized input deny. These are in-memory value bounds, not a raw-file parser or ingress boundary.
3. **Signature semantics.** Ed25519 verification proves a signature over the hexadecimal canonical payload digest encoded as UTF-8 under a separately supplied trusted key. It reports `artifact_signer_verified`. It does not authenticate original file bytes, provider/payment/reply facts, source completeness, sender mappings or storage outside all backups; those positive claims remain false.
4. **Offline planning and rehearsal labels.** Planning now checks exact review-result binding, workspace/epoch consistency, distinct epochs and strict boolean assertions. Authority-input review checks plan integrity and elementary epoch/control/review invariants, root scope, unique authority IDs, stopped status and generation-reference shape. Independent review additionally found that a rehashed plan could bypass some invariants; seven regressions reproduced that issue before its correction. Passing these input checks never sets `reactivation_ready`, `rehearsal_passed`, `transaction_exercised`, `committed` or `activation_allowed`. The legacy `rehearse_transaction` function performs no database transaction.
5. **Reply metadata.** Validation rejects duplicate events/record IDs, invalid calendars, non-UTC or future observations and descending observations for a sender/recipient pair within one supplied batch. One captured clock reading bounds the batch. Passing reports only `reply_metadata_valid`; source authentication, sender mapping, restored history and activation remain false. This helper neither compares other batches nor writes suppression records.
6. **Async test invocation.** Disabling automatic pytest plugins without explicitly loading pytest-asyncio skipped async tests. The verification invocation now loads that plugin and uses auto async mode. Those earlier skips are not treated as execution evidence.

## Verification evidence

The initial adversarial run reproduced 22 failures in 23 cases before the main corrections. A later independent finding reproduced seven additional planner-invariant failures before its fix. The final focused suite includes the 15 updated original tests and 80 adversarial cases.

Final verification on the corrected source:

- **95 focused tests passed** in 4.04 seconds, with one existing multipart deprecation warning. Statement coverage: activation 99%, reconciliation 95%, reply metadata 98%; combined 97% (285/294 statements). Coverage data was written to a separate temporary file, preserving the existing workspace coverage file.
- **841 restore regression tests passed, two skipped** in 149.71 seconds, with the same existing warning. Native tests used the isolated MongoDB replica set. The two skipped tests are the separately enabled physical backup/restore drills; no fresh archive/restore rehearsal is claimed. An earlier full run before the final seven planner regressions passed 834 cases with the same two skips.
- Explicit plugin invocation: `OUTREACH_TEST_LOCAL_MONGO=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin -o asyncio_mode=auto -q tests/test_outreach_restore*.py`. The focused coverage run loads `pytest_cov.plugin` explicitly as well.
- Scoped Python compilation, Bandit medium/high checks and whitespace checks passed. Optional formatting/type-check tools were unavailable. Frontend and full-application checks were not rerun because the changes are isolated offline helpers; no broader release certification is claimed.
- Independent Python review reran all 95 helper cases successfully in 1.35 seconds, passed Bandit and verified that the rehashed-plan probes now deny. Its remaining report wording correction was applied: selected metadata equality never establishes completeness. No material source/contract finding remains.

Owned MongoDB PID 53245 was verified against its exact command and two ownership manifests before cleanup. No temporary databases remained. That process, its storage and the temporary owner manifest were removed; loopback ports 27028, 27029 and 6389 are closed. The existing user MongoDB process was preserved. No Redis service was started.

The native restore regression uses an isolated loopback MongoDB replica set, synthetic databases and the established opt-in native test harness. It exercises the existing database-backed restore protections; it does not turn the offline dictionary review into a database activation rehearsal. Physical archive/restore drills require a separate opt-in and are explicitly reported as skipped when absent.

## Remaining implementation

Authenticated outside-backup financial/provider/resource facts and completeness manifests, original sender/reply mapping and actual suppression recovery remain pending. A real snapshot/CAS activation implementation and operational restart/restore drills must follow those facts. Older credential/voice/proxy cases, explicit integration activation, actual IAM/kernel egress verification, a controlled live pilot and release/deployment validation retain their existing scope; this reverification does not complete them.

## Preservation and operational scope

The three architecture documents and matching Desktop copies carry the corrected v2.54 scope and byte-match. All 177 relative Markdown links in those documents and the five relevant reports resolve. The four earlier v2.51–v2.54 reports explicitly withdraw unsupported claims and link here. A private pre-edit source/document backup is retained at `/var/folders/v_/hqdkw39d5yg6d_8gk__sjdmm0000gn/T/unravler-reverify-v254-rqzlx1ha`.

All changes are local. No commit, push, deployment, real AWS/provider request, purchase, production grant or flag change was made. No frontend change was made. Unrelated worktrees, wedding artifacts and the existing coverage file were preserved. Session memory is updated after final verification and cleanup.
