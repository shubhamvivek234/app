# Unravler.io v2.55 — lead workspace isolation

Date: 11 October 2026. Status: implemented and verified locally; not committed or deployed.

This repairs F1 from the [outreach audit](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_OUTREACH_AUDIT_2026_10_10.md). The application deployment remains `e506747cc25f2dd400250c7a8af0b60037a449a3`; checkout `cc01f4477765cc27a8205dfeec0d38c301f63756` contains the earlier documentation follow-up. This report records working-tree changes, not a new deployed release.

## Result

A lead or campaign's creator no longer grants access through another workspace. Lead list/export, activity, stage, notes, pause/resume, deletion and campaign intake checks require the authorized workspace. Missing, null and array-valued resource workspace scopes do not qualify. Legacy records are not adopted, deleted or automatically repaired. An explicitly authorized personal workspace whose ID equals the user ID still works; equality of those IDs alone grants nothing.

All 22 lead routes consume the user context returned by the actual workspace/role dependency. The same resolved workspace is checked for deletion closure before resource access. This closes a second mismatch where the permission dependency could resolve a former member to workspace A while the handler still queried stale workspace B. Read routes now explicitly require `lead:read`.

The [shared scope helper](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/workspace_scope.py:5) includes workspace equality and absence of `workspace_id.0`. Mongo equality alone also matches array members; the additional predicate rejects nonempty array aliases, while empty arrays cannot equal the required string. Native tests verify this behavior for leads, campaigns and import jobs. Caller workspace identity must itself be a nonblank string.

Subsidiary activity sender/campaign/task/thread/note reads, search-job admission/cancellation, staged name edits, campaign counters and relevant positive importer reads also carry workspace scope. Staged commit verifies the job's campaign in that workspace before modifying leads. Cancellation can still stop an owned job whose campaign is no longer available; it never grants execution.

The [common importer](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/lead_importer.py:1064) now updates campaign counts with workspace scope. Independent review reproduced an ID-only update changing a foreign campaign when legacy campaign IDs collided. CSV and URL regression tests now verify the authorized counter changes while foreign and ambiguous counters remain untouched.

## Verification

- **349 backend checks passed** in the final 19-module selection, including **74 new route/scope cases**. Authentication and database transport are replaced in the new offline tests; actual workspace resolution, role permissions, deletion admission and query matching are exercised. No new offline cases use the shared legacy authorization stubs.
- **14 additional native Mongo checks passed** against a newly launched, loopback-only disposable standalone process on an ephemeral port. They exercise actual queries/HTTP handlers, export, foreign mutations, ambiguous lead/campaign/job scopes, stale workspace deletion admission and CSV/URL counter isolation. The process is owned by its fixture; generated databases are dropped, the fixture asserts none remain, and the process/storage are removed.
- Independent Python/security review approved the final repair with no remaining HIGH/CRITICAL findings. Its separate 113-check run included the 14 native cases; a later 109-check offline rerun included the scope validation and mocked end-to-end fixture correction. These overlap the parent verification and are not added to its total.
- Changed executable-statement coverage: leads API **51/52 (98.1%)**, importer **1/1**, new scope helper **5/5**; total **57/58 (98.3%)**. The new helper has 100% statement/branch coverage. Whole-module statement coverage is 81.5% for the API and 82.6% for the importer; their broader branch coverage is lower and is not claimed complete.
- Scoped medium/high Bandit, Python compilation and whitespace checks pass. One existing multipart deprecation warning remains.

The native and offline parent selections contain **363 distinct passing checks**. No frontend source changed; the prior 99 frontend checks/build were not rerun for this backend repair. No authenticated browser flow, replica-set transaction race, Redis crash drill, provider action or production data inspection is claimed.

The initial regression tests reproduced the creator bypass before source changes. Independent review then found the array-alias and importer-counter gaps; both received failing reproductions before correction. A legacy search-test collection now uses the same query matcher as its existing reads so it understands the additional predicate. A combined regression run exposed an existing encryption-fixture mismatch: the mocked inbox cookie was encrypted directly from the environment, whereas the app uses a cached key. The test now uses its already-imported production encryption helper. Assertions and production cryptography were not weakened. The final combined selection passes.

## Limits and next work

This patch addresses customer-facing lead resource admission and the shared importer's subsidiary campaign write. It does not audit every other application resource or serialize a permission check with a later membership revocation. A request already admitted can complete; transactionally ordering revocation across all product APIs remains a separate design decision. Native standalone query checks do not establish execution transaction guarantees.

There is no production census or evidence of exploitation. Ambiguous legacy rows may disappear from customer views and require a separately reviewed ownership migration; the patch does not infer ownership from creator identity. No schema/index migration, grant, flag/config change, live action, provider/AWS call or purchase was performed. All unrelated existing working-tree changes are preserved.

F2–F9 and the operational audit recommendations remain pending. The next bounded fix is conversation-bound inbox drafts, followed by Sheets/common enrollment repairs. The security/release, authenticated recovery/activation, custody and actual pilot requirements remain as recorded in the audit.

## Reproduction

From the repository root, run the native and local scope checks with the installed virtual environment:

```sh
OUTREACH_TEST_LOCAL_MONGO=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  -p pytest_asyncio.plugin -o asyncio_mode=auto \
  tests/test_outreach_lead_workspace_scope.py \
  tests/test_outreach_lead_workspace_scope_mongo.py -q
```

The native fixture requires a local `mongod` executable and starts its own isolated process. It never connects to a pre-existing database. The offline scope suite can run without the opt-in flag or native test module.
