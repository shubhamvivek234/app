# Unravler.io Restore Provenance and Reactivation Plan Release — v2.52

## Scope

**Reverification correction:** Ed25519 authenticates the canonical payload digest and artifact signer against an operator-trusted public key supplied out of band. It does not authenticate provider/payment/reply facts or completeness. `artifact_signer_verified` reflects this narrow result; `source_provenance_verified` remains false. Corrected code actually compares the required independent local view, which the original signed verifier ignored.

`plan_reactivation` checks supplied offline values: exact workspace/current epoch, distinct new epoch, review digest equal to the supplied reconciliation-result digest, strict control booleans, selected group matches and artifact-signer status. These are caller assertions, not verified fleet/credential/provider state. It reports `input_checks_passed` only. `reactivation_ready` and `activation_allowed` always remain false, with actual transactional activation and live verification pending.

## Verification

The historical eight-test run did not establish those stronger claims. Corrected adversarial tests cover signature tampering/wrong keys, independent-view mismatch and exact control/scope/review validation. Final results: [reverification report](UNRAVLER_IO_RESTORE_HELPERS_REVERIFICATION.md). No provider/AWS, credential, grant, production restore, live-action or deployment operation was performed.
