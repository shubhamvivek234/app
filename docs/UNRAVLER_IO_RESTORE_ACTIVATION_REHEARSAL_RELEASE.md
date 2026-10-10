# Unravler.io Restore Activation Rehearsal Release — v2.53

## Scope

**Reverification correction:** `rehearse_transaction` is an offline dictionary-input checker despite its legacy name. It exercises no transaction and cannot detect database races or prove current authority. It checks supplied plan/root/selected authority consistency, including exact elementary plan invariants even if a caller recomputes the plan digest.

Only `input_checks_passed` can be true. `transaction_exercised`, `rehearsal_passed`, `committed` and `activation_allowed` always remain false. The receipt digest identifies supplied input content, not an authenticated database transaction. Actual transactional activation, CAS/concurrency ordering, complete authority coverage and restart drills remain unimplemented here. The existing restored-execution denial gate is unchanged.

## Verification

The historical ten-test run only exercised supplied dictionaries, not successful/raced database transactions. Corrected tests enforce truthful result labels, plan/authority input validation and changed/rehashed malformed plans. Results: [reverification report](UNRAVLER_IO_RESTORE_HELPERS_REVERIFICATION.md). No production authority, provider/AWS, credential, grant, live-action or deployment operation was performed.
