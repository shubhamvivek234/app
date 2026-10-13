# Unravler.io v2.56 — authorized workspace context and prompt isolation

Date: 12 October 2026 (IST). Status: implemented and verified locally; uncommitted and undeployed. Base checkout: `main` at `3fc64f70cea68dbaf19aefaf349020d5c9c789a3`.

This closes A01 and A02 locally from the [section audit](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_SECTION_BY_SECTION_AUDIT_2026_10_11.md). It also removes A16's invented curated-prompt run counts; A16's billing/header issues remain open. Production remains on the previously recorded v2.55 application release.

## Result

The [shared outreach dependency](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/dependencies.py:24) returns the actual user/workspace copy approved by the existing role dependency, validates a nonblank scalar workspace ID, and checks that same workspace for deletion closure. Handlers consume that returned context. It does not substitute creator IDs for missing tenant identity or mutate the cached authentication dictionary.

All **157 ordinary outreach handlers** use canonical admission: 155 handlers with a user argument, the parent overview and the pure sequence validator. Existing explicit mutation/read permission names are preserved; ordinary reads without an explicit granular permission use `workspace:read`. Leads retain their 22 existing granular permissions through the shared helper. The stale parent-router deletion check is removed from production mounting after testing the complete route graph. Its import-compatible adapter remains for older tools/tests, using the canonical read dependency.

OAuth callbacks retain state/browser binding. The seven public API-key handlers keep their separate key/scope and deletion authorities. The unauthenticated health diagnostic remains separate. Integration mounting/configuration and execution flags are unchanged. The route-graph test checks optional integration routes even when their mount flag is disabled.

Six existing protected Team handlers now consume the context returned by their permission dependency. Invitation creation still requires verified email. The approval-policy update previously referenced undefined `team:manage`, causing a permission lookup error even for an owner; it now requires the existing `workspace:update` admin permission, consistent with role management. Owner/admin updates succeed, editor/viewer updates are denied, and native fallback tests cover all six Team handlers without modifying foreign members, invites or policy records. Invitation creation/link serialization is tested; email delivery is not.

[Prompt library](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/prompts.py:97), [deletion](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/prompts.py:143) and [lead preview](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/prompts.py:165) require strict scalar current-workspace scope. Creator identity, UID aliases, missing/null scope and array aliases grant no access. Current-workspace records from another creator remain accessible to an appropriately permitted member. Preview remains illustrative and does not execute an AI instruction or send outreach.

The five curated templates are server-owned definitions with stable reserved IDs. Library reads return a fresh copy plus up to 100 current-workspace custom prompts; they perform no inserts. A database row declaring `is_system=true` cannot become a global template. Historical seeded rows are retained but excluded, avoiding duplicates and fabricated usage; custom rows with a missing system flag remain compatible as workspace-scoped custom records. Reserved catalog IDs cannot be shadowed or deleted through custom prompt endpoints. Curated run counts are zero; no usage is invented. The existing frontend displays its Curated label without a frontend source change.

## Verification

- **823 distinct backend checks passed:** 791 in the affected 53-module offline regression selection (52 in the recorded manifest plus `tests/test_team_route.py` supplied separately), plus 32 native checks. The offline selection skips 194 opt-in/historical drills rather than claiming their execution. The native checks comprise 18 new context/prompt/Team cases and the existing 14 lead-isolation cases; overlaps with focused and coverage runs are counted once.
- **200 new acceptance cases:** 182 offline HTTP/context checks and 18 native cases. The immutable 155-handler contract verifies final-selected-tenant deletion stops through actual dependency resolution. Additional checks cover overview/validation admission, route-graph exceptions, viewer/admin fallback, role downgrade, strict prompt scopes, catalog stability, current-member workflows and verified-email preservation.
- **307 focused checks passed** with native Mongo enabled, including existing lead and onboarding regressions. A separate 210-check coverage selection overlaps these checks: shared dependency coverage **100%**, prompt module **99%**, combined **99%** statement coverage. This is not coverage of every changed API module or every permission race.
- **99 frontend component tests passed across 22 suites.** Frontend application source is unchanged; no new production frontend build or authenticated browser journey is claimed.
- Independent Python/security review approved the bounded application change with no remaining HIGH/CRITICAL findings. It verified all **117 pre-existing explicit permission contracts**, with the sole intended Team permission-name correction, and the complete production/optional route graph. Its 414 distinct selected offline checks overlap parent runs and are not added to the total. Native cases were independently source-reviewed, not independently rerun.
- Python compilation of all 23 changed/new Python files, scoped medium/high Bandit and whitespace checks passed. Existing multipart/Node test warnings remain. Coverage output was kept outside the repository; the unrelated root coverage file was preserved.

New tests first reproduced the cross-workspace mutation and prompt leaks before implementation. Team red tests also reproduced the undefined permission error. An initial native test helper incorrectly expected removed membership to remain present on its second request; it now captures the initial authenticated snapshot once and returns copies. Two added Team controls initially used an incomplete invite fixture and a fake collection without native projection support; they were moved to real Mongo with complete synthetic invite data. An older retired-login HTTP test needed a database dependency stub for the new read admission; its malformed-body/410 assertions remain unchanged. No production check was weakened to satisfy these fixtures.

Native tests launch their own standalone Mongo processes bound only to loopback on ephemeral ports. Generated databases are dropped, and each fixture asserts its database namespace is clean before removing its owned process/storage. The user's pre-existing Mongo process is untouched. Native queries and HTTP fallback timing do not establish replica-set serialization, crash recovery or production exploitation.

## Limits and next work

A01/A02 are locally repaired; **17 audit groups remain open**. A15's ongoing activity-stream access revalidation is the next bounded security fix. An ordinary request's canonical admission does not revalidate a stream for its lifetime or transactionally order every later membership/deletion change with every write. Security/CI failures and enforceable native/browser checks remain release blockers; this selection does not certify the full backend or combined release.

No schema/index/data migration, real credential opening, production census, live provider/AWS call, purchase, grant or execution/integration flag change was performed. Legacy unproven records are not adopted or erased. No commit, push or deployment was performed. Unrelated worktrees, wedding files and earlier local documentation changes were preserved.

Authenticated external-source recovery/completeness, sender/reply mapping and suppression recovery, transactional activation drills, remaining custody/legacy migrations and health/IAM/egress/pilot verification remain unfinished. The v2.51–v2.54 helpers remain offline selected-metadata/signature/input validators and cannot authorize restart.

## Reproduction and evidence

```sh
OUTREACH_TEST_LOCAL_MONGO=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  -p pytest_asyncio.plugin -o asyncio_mode=auto -q \
  tests/test_outreach_authorized_context.py \
  tests/test_outreach_authorized_context_mongo.py \
  tests/test_outreach_lead_workspace_scope.py \
  tests/test_outreach_lead_workspace_scope_mongo.py \
  tests/test_outreach_onboarding_audit.py
```

The native fixture requires a local `mongod`; it never connects to a pre-existing database. Omit native modules/opt-in to run only offline tests. Temporary evidence: `/tmp/unravler-access-fix-20261011/` contains the pre-change source/route contract, initial red logs, affected selection, focused/native/coverage/frontend results and final verification metadata. Temporary paths may be cleaned; source/tests and this report retain the reproducible contract when the local change is later released.
