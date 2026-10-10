# Unravler.io v2.55 — lead workspace isolation

Date: 11 October 2026. Status: committed, pushed and verified on EC2; both Vercel production deployments succeeded.

This repairs F1 from the [outreach audit](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_OUTREACH_AUDIT_2026_10_10.md). Application commit `b85b2df8cdc3faf29a63a021fb9a3144db5f684f` is deployed. The subsequent `648efd1` correction changes one test fixture only; documentation follow-ups do not change runtime application files.

## Result

A lead or campaign's creator no longer grants access through another workspace. Lead list/export, activity, stage, notes, pause/resume, deletion and campaign intake checks require the authorized workspace. Missing, null and array-valued resource workspace scopes do not qualify. Legacy records are not adopted, deleted or automatically repaired. An explicitly authorized personal workspace whose ID equals the user ID still works; equality of those IDs alone grants nothing.

All 22 lead routes consume the user context returned by the actual workspace/role dependency. The same resolved workspace is checked for deletion closure before resource access. This closes a second mismatch where the permission dependency could resolve a former member to workspace A while the handler still queried stale workspace B. Read routes now explicitly require `lead:read`.

The [shared scope helper](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/workspace_scope.py:5) includes workspace equality and absence of `workspace_id.0`. Mongo equality alone also matches array members; the additional predicate rejects nonempty array aliases, while empty arrays cannot equal the required string. Native tests verify this behavior for leads, campaigns and import jobs. Caller workspace identity must itself be a nonblank string.

Subsidiary activity sender/campaign/task/thread/note reads, search-job admission/cancellation, staged name edits, campaign counters and relevant positive importer reads also carry workspace scope. Staged commit verifies the job's campaign in that workspace before modifying leads. Cancellation can still stop an owned job whose campaign is no longer available; it never grants execution.

The [common importer](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/lead_importer.py:1064) now updates campaign counts with workspace scope. Independent review reproduced an ID-only update changing a foreign campaign when legacy campaign IDs collided. CSV and URL regression tests now verify the authorized counter changes while foreign and ambiguous counters remain untouched.

## Verification

- **349 backend checks passed** in the original 19-module repair selection, including **74 new route/scope cases**. Authentication and database transport are replaced in the new offline tests; actual workspace resolution, role permissions, deletion admission and query matching are exercised. No new offline cases use the shared legacy authorization stubs.
- **14 additional native Mongo checks passed** against a newly launched, loopback-only disposable standalone process on an ephemeral port. They exercise actual queries/HTTP handlers, export, foreign mutations, ambiguous lead/campaign/job scopes, stale workspace deletion admission and CSV/URL counter isolation. The process is owned by its fixture; generated databases are dropped, the fixture asserts none remain, and the process/storage are removed.
- Independent Python/security review approved the final repair with no remaining HIGH/CRITICAL findings. Its separate 113-check run included the 14 native cases; a later 109-check offline rerun included the scope validation and mocked end-to-end fixture correction. These overlap the parent verification and are not added to its total.
- Changed executable-statement coverage: leads API **51/52 (98.1%)**, importer **1/1**, new scope helper **5/5**; total **57/58 (98.3%)**. The new helper has 100% statement/branch coverage. Whole-module statement coverage is 81.5% for the API and 82.6% for the importer; their broader branch coverage is lower and is not claimed complete.
- Scoped medium/high Bandit, Python compilation and whitespace checks pass. One existing multipart deprecation warning remains.

The original native and offline parent selections contained **363 distinct passing checks**; the deployment follow-up below expands this selection. No frontend source changed; the prior 99 frontend tests were not rerun for this backend repair; deployment builds are recorded below. No authenticated browser flow, replica-set transaction race, Redis crash drill, provider action or production data inspection is claimed.

The initial regression tests reproduced the creator bypass before source changes. Independent review then found the array-alias and importer-counter gaps; both received failing reproductions before correction. A legacy search-test collection now uses the same query matcher as its existing reads so it understands the additional predicate. A combined regression run exposed an existing encryption-fixture mismatch: the mocked inbox cookie was encrypted directly from the environment, whereas the app uses a cached key. The test now uses its already-imported production encryption helper. Assertions and production cryptography were not weakened. The final combined selection passes.

## Limits and next work

This patch addresses customer-facing lead resource admission and the shared importer's subsidiary campaign write. It does not audit every other application resource or serialize a permission check with a later membership revocation. A request already admitted can complete; transactionally ordering revocation across all product APIs remains a separate design decision. Native standalone query checks do not establish execution transaction guarantees.

There is no production census or evidence of exploitation. Ambiguous legacy rows may disappear from customer views and require a separately reviewed ownership migration; the patch does not infer ownership from creator identity. No schema/index migration, grant, flag/config change, live outreach action, credential/AWS API call or purchase was performed. All unrelated existing working-tree changes are preserved.

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

## Authorized deployment — 11 October 2026

Application commit `b85b2df8cdc3faf29a63a021fb9a3144db5f684f` was pushed to `origin/main` and fast-forwarded on EC2. All five Python service images were rebuilt sequentially. The previous images remain tagged `rollback-e506747-v255`; the unchanged MCP image was retained. All three workers reported zero active tasks before the graceful stop. Beat stopped first, then workers; API passed health before workers restarted one at a time, followed by beat. This is rollout supervision, not a certified restore/custody drain.

Verification confirmed:

- The three changed production source files match the application commit byte-for-byte in all five Python containers. Every new image also passed an isolated, network-disabled compilation/scope-helper smoke check before installation. Runtime PyJWT remains 2.15.1.
- API and MCP are healthy; all three expected worker identities answer `pong`, and beat runs. All six application services have zero restarts at inspection.
- Internal health is OK. Readiness reports MongoDB, both Redis checks, Firebase admin and R2 storage OK, with the unchanged password-reset custom-link-domain warning.
- Production environment/Compose fingerprints and selected enabled flags match the baseline. Live outreach remains false; the pre-existing integration flag remains true. No integration activation or provider pilot was performed.
- Public unauthenticated lead access returns HTTP 401. CORS preflight from `https://www.unravler.com` returns 200 with that exact origin and credentials allowed.
- Both [app production deployment](https://vercel.com/findshubhamss-3533s-projects/app/nLHLK7VwskKxRCzXHQ7PP5XDRShR) and [app-fgv2 production deployment](https://vercel.com/findshubhamss-3533s-projects/app-fgv2/65921qZgn7whpciPQXUoNdc7jkNm) report success for the exact application commit. GitHub production deployment IDs are `6988203785` and `6988177876`. Both public login URLs return 200 and serve `main.6028c603.js`. No frontend source changed; this does not establish an authenticated browser journey.

An 89-check precommit subset passed. The [application CI run](https://github.com/shubhamvivek234/app/actions/runs/38094081352) passed its frontend build but stopped its backend job after five failures: 1,234 passed, 298 skipped and six deselected. Three welcome-email/magic-link failures reproduce identically on the prior committed baseline `cc01f44` and the new source: an awaited MagicMock and missing fake account-erasure collections. These remain unresolved. Two parity tests exposed a fake query matcher that did not understand the new scope predicate. Correcting its reads also exposed the same problem in its update matcher; `648efd1` updates both to the existing shared matcher. All original unsupported-feature/no-write/stage-mutation assertions remain intact; production checks are unchanged.

After the fixture correction, the expanded 20-module selection passes **359 checks**, including all ten parity tests; independent parity/scope review passes **84 checks** and approves the delta. These runs overlap the original 349 checks. Together with the earlier unchanged 14 native checks, the bounded parent evidence covers **373 distinct passing checks**. No fresh native database or frontend-test rerun is claimed for the test-only follow-up. The [test-only follow-up CI run](https://github.com/shubhamvivek234/app/actions/runs/38094578259) is still in progress at inspection; no combined green result is claimed. Its [security run](https://github.com/shubhamvivek234/app/actions/runs/38094578266) has already failed Python audit, SAST and Trivy, with TruffleHog passing and NPM audit still running. Documentation-only commits skip duplicate workflows and do not bypass these application checks.

The [application security run](https://github.com/shubhamvivek234/app/actions/runs/38094081399) remains red for dependency audits, existing SAST findings and container scanning; TruffleHog passes. Wider security findings and F2–F9 remain open. This is not a green combined release or completion of authenticated recovery/activation and operational requirements.

Metadata-only runtime verification is saved on EC2 and locally at `/tmp/unravler-v255-rollout-verification.json`; public checks are at `/tmp/unravler-v255-public-verification.json` locally. Unrelated local/remote worktrees and files were preserved.
