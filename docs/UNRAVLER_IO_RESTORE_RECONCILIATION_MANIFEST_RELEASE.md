# Unravler.io Restore Reconciliation Manifest Release — v2.51

## Scope

**Reverification correction:** This is an offline selected-status comparison helper, without a database snapshot/export/import integration. It requires a separate caller-supplied local view, exact workspace/epoch, an out-of-band canonical payload digest, unique source/record descriptors, strict schemas and bounded JSON values. Sources must describe all three groups. Selected rows contain only `record_id` and `state`; they do not reconstruct payment terms or provider/reply history.

The original code compared the manifest's summaries with metadata inside the same manifest, falsely reporting completeness. Corrected code compares the independent view as well and reports only `selected_metadata_matches`; `completeness_verified` always remains false. Global source review remains required even for an empty or matching selection. It cannot enforce independent origin, prove storage outside all backups, or authenticate source facts.

## Verification

The historical five-test run did not cover the independent-view flaw. Corrected focused and restore regression results, failure reproductions, and exact boundaries are in [reverification report](UNRAVLER_IO_RESTORE_HELPERS_REVERIFICATION.md). Async tests explicitly load `pytest_asyncio.plugin`; disabling plugin autoload alone silently skipped those tests.

This helper performs no database, provider, AWS, credential, grant, live-action, restore or deployment operation. Reverification also runs the existing restore regression against an isolated local MongoDB, as recorded in the linked report. Existing unrelated worktree changes were preserved. This contract is a canonical integrity and selected-metadata equality check only; source authenticity and positive reactivation remain separate slices.
