# Unravler outreach: section-by-section audit — 11 October 2026

Reviewed checkout: `3fc64f70cea68dbaf19aefaf349020d5c9c789a3` (`main`). The latest recorded deployed application change is v2.55 Leads isolation repair, `b85b2df`; subsequent commits change tests/documentation. This report supersedes the earlier audit's pending-work list, while preserving its historical evidence.

## Local implementation update — v2.61 (13 October 2026 IST)

Local email-reporting repair, 2026-10-13 (IST): [v2.61 verification and limits](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_EMAIL_EVIDENCE_REPORTING_RELEASE.md) records bounded A13 repair. Current provider acceptances use stable scoped operations and original accepted_at, never completed-task projections or no-bounce delivery. Exact operation/workspace/sender joins preserve recorded message-reference bounces; thread/address matches remain possible. Human assertions, contradictory/legacy projections and unusable evidence stay separate. Delivery/submission and deliverability remain null/unavailable. Bounded read failure/overflow invalidates email counts; fixed as_of is a timestamp cutoff, not a snapshot or authenticated completeness proof. API/UI/CSV preserve unknown/partial status and original dates. Fresh 3,357 combined non-sandbox checks plus 347 enabled native cases (3,704 distinct), 177 frontend tests, five synthetic-API Chromium checks and production build pass; native skips are zero. The 63 new native cases give 97% module coverage; independent bounded source review approves. Three application groups remain: A14 cohort rates, A15 P2 feed and A18 voice. Security/legacy/authenticated recovery/activation/live/IAM/egress/pilot/release gates remain open. Local only; no commit/push/deployment/live enablement or real provider/AWS calls. Earlier checkpoint counts below remain historical.

## Historical implementation checkpoint — v2.60 (13 October 2026 IST)

**A11 now has a bounded local readiness repair. Four application groups remain: A13, A14, A15 P2 and A18.** See [shared admission, review behavior and verified limits](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_CAMPAIGN_READINESS_RELEASE.md). Read-only stored/prospective preflight and launch share known prerequisites; the wizard uses the real DTO, discards stale checks and rechecks saved inputs. Eligibility does not grant execution or certify fresh health, approvals or key access. Fresh 3,357 combined non-sandbox checks plus 284 separately enabled native cases pass (3,641 distinct); native skips are zero. All 174 frontend tests, four compiled-component/synthetic-API Chromium checks and production build pass. Independent bounded source/contracts review approves; current coverage/scans/evidence are in the release. Security/old-data/authenticated recovery/activation/live/IAM/egress/pilot/release gates remain open. Local only; no commit/deployment/live enablement.

## Historical implementation checkpoint — 12 October 2026 (IST)

**A01 and A02 are fixed locally in v2.56; 17 finding groups remain open.** See [v2.56 verification and limits](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_AUTHORIZED_CONTEXT_AND_PROMPT_ISOLATION_RELEASE.md). The 823 distinct backend checks include 32 native Mongo checks; 99 frontend component tests also pass. Independent review approved the bounded change. It is uncommitted and undeployed; production remains on the recorded v2.55 application release. A16's invented curated-prompt usage is removed, while its billing/header defects remain open. At v2.56, A15 ongoing stream access was next; the v2.57 update below records its repair. Security/CI hardening remains pending. The historical audit/review findings below describe the earlier source and preserve their original evidence; their “19 open” and “no application changes” statements apply to those review dates, before this implementation.

## Historical implementation checkpoint — v2.57 (12 October 2026 IST)

**A15's P1 access-lifetime portion is fixed locally; its P2 delivery/completeness portion remains open. The open-group count stays 17.** See [v2.57 verification and limits](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_ACTIVITY_STREAM_ACCESS_RELEASE.md). The original actor/workspace is revalidated against current primary/majority authorities before task reads and each event, including already-buffered rows. Access stops/read failures end the generator with a sanitized control; Home closes the connection and clears cached activity. A 300-second generator deadline and bounded reads apply; this does not atomically order revocation with sending or guarantee socket closure under backpressure.

Fresh evidence: 864 distinct selected backend checks (815 offline plus 49 native, including 17 new stream cases/two loopback HTTP closures), 102 frontend component checks and the production frontend build pass. There are 41 new backend cases, and helper statement coverage is 97%. Independent review approves the bounded source change. Native authentication transport is synthetic; there is no fresh authenticated browser, replica/crash, production/provider/AWS, grant, flag, commit, push or deployment proof. The preceding v2.56 work and unrelated local files are preserved. Security/CI hardening is the remaining first-wave priority, followed by the recorded customer-flow fixes. Historical findings below remain baseline evidence, with local status called out where repaired.

## Historical implementation checkpoint — v2.59 (12 October 2026 IST)

**At v2.59, A12 received a bounded local repair. Five application groups remained unfinished: A11, A13, A14, A15 P2 and A18.** See [v2.59 behavior and verification](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_SENDER_RECOVERY_RELEASE.md). Recovery requires eligible elapsed-cooldown state, usable stored material, current resources and no selected holds; it leaves tasks/campaigns paused and grants nothing. Tenant-safe stop helpers preserve foreign same-ID records. The final A09 null-to-missing profile binding gap is corrected explicitly. Independent review approves the bounded source; fresh 3,356 combined non-sandbox checks plus 219 enabled native cases pass (3,575 distinct), with no native skips. The combined run skips 1,011 opt-in/historical cases, deselects six sandbox cases and reports 15 warnings. This is not fresh provider authentication/health, transactional restore activation or live verification. Current combined results are in the linked report; earlier release counts below remain historical checkpoints. Security, old-data migration and operational gates remain open. Local only; no commit/deployment/live enablement.

## Historical implementation checkpoint — v2.58 (12 October 2026 IST)

**A03–A10, A16, A17 and A19 now have bounded local current-path repairs. Six groups remain unfinished: A11, A12, A13, A14, A15 P2 and A18.** See [v2.58 behavior, verification and limits](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_OUTREACH_CUSTOMER_FLOW_REPAIRS_RELEASE.md). Current replies bind recipient/revision and recover unknown request references; common intake and warm-up edits use ordered admission; deletion has stop-first resumable journals without automatic reauthorization; Engage projections fence original list/contact/run generations. Crawl/billing cancellation, BSON lists, visible loading/billing state and style failure reporting are corrected. Older incomplete enrollments, orphan Engage data and unproven deletion history remain separate migration/review work.

Fresh verification: 3,356 combined non-sandbox backend checks pass (936 opt-in/historical skips, six sandbox deselections, 15 warnings), plus 144 separately enabled native checks with no skips = **3,500 distinct backend checks**. 128 outreach frontend checks/26 suites, two compiled-Inbox Chromium cases with synthetic APIs and the production build pass. Independent source/test review approves the bounded repairs. Python dependency audit in a fresh environment reports no known vulnerabilities and scoped Bandit has zero findings; npm retains 116 findings including 69 high, and Semgrep retains 35 warnings. Native/browser CI checks are implemented locally; remote runs, protected required checks and container/live security remain unverified. No commit, push, deployment, provider/AWS calls, grants, purchases or live flag changes. Earlier release counts and the baseline defects below remain historical evidence.

## Assessment at the audited baseline

The outreach application still needs fixes before an expanded customer pilot. Keep the existing FastAPI, MongoDB, Celery and React architecture. The most urgent defect is a surviving workspace-data leak through prompt preview/library routes. Ordinary customer journeys also have incorrect conversation drafts, broken imports, incomplete enrollment, misleading readiness/reporting and interruption/deletion problems.

This was an audit, not an implementation or deployment. No application source, configuration, live flags, grants, production data or external provider resources were changed. The report and architecture cross-references are documentation changes. Temporary component probes were removed from the checkout.

## First-pass coverage and evidence (retained)

- Inventoried **166 router-decorated handlers** under `outreach/api/`, including experimental routes. Reviewed all nine top-level outreach screens, campaign wizard/detail/sequence/import flows, eight Settings sections, their API paths and relevant workers/core guards. Inventory does not mean every handler, branch or provider combination was executed.
- Fresh parent regression runs: **512 existing backend tests passed** across 35 selected modules, with **118 opt-in tests skipped** in the second run. Separately, **14 real MongoDB scope tests passed** using an owned disposable loopback server. These are **526 distinct passing backend checks**, not a full backend certification.
- **99 existing frontend tests passed** across 22 suites. Four additional temporary component probes reproduced draft transfer, a fabricated trial, failed billing loading presented as no paid access, and failed crawl cancellation presented as stopped. These probes assert current incorrect behavior; they are not acceptance tests for fixes.
- Eleven parent synthetic backend probe groups reproduced delete interruption, a workspace-context race, two search-commit cases, both Sheets errors, public enrollment, readiness disagreement, analytics errors, activity loss, false cancellation acknowledgement after a lost compare-and-set, and silent style fallback. An independent Python reviewer supplied additional HTTP/service probes and **158 passing focused tests**; overlapping independent tests are not added to the parent count. Final independent source/probe/report review approved the bounded findings after correcting the email-task evidence wording.
- Current Leads isolation has fresh native database evidence. No fresh replica-set transaction race, Redis/SIGKILL redelivery, physical backup/restore, authenticated browser journey, AWS/network control check or real provider/pilot test was performed. Historical evidence remains in the release reports. Provider/admission substitutions in individual probes are described below.
- Initial backend test collection hit an unrelated installed-plugin `pkg_resources` error; the final runs used explicit pytest-asyncio with plugin autoload disabled, matching CI's invocation model. Existing multipart/Node warnings remain. Independent scoped Bandit found no medium/high issues; this does not detect the semantic failures below. Existing root `.coverage` and unrelated worktrees/wedding artifacts were preserved.

## Second review before implementation — 11 October 2026

The user requested another review before code changes. Application implementation remains paused. All **19 finding groups remain open**; the second review strengthens several reproductions and narrows the limits below. It does not add an implementation release or authorize live execution.

Fresh verification:

- All **195 application/source fingerprints** recorded in the first audit still match. The earlier passing tests remain evidence for that source, but their counts are not presented as fresh reruns.
- The **11 backend probe groups reproduced again**, with non-loopback socket connections denied in the probe process.
- **13 additional diagnostic tests passed against an owned disposable native MongoDB**: five prompt scope variants plus prompt library/deletion, the actual permission-fallback race, stale parent-router erasure rejection, two enrollment/scheduler controls, preflight using actual paid-access/readiness code, analytics, and ongoing stream access after membership removal. Passing these diagnostics means the current defect was reproduced, not fixed. The initial preflight fixture used an already-active campaign and hit the earlier 409 guard; it was corrected to a draft campaign and the complete 13-case rerun passed. No replica-set concurrency or physical-call claim is made.
- **99 existing frontend tests and five temporary component probes passed** (104 total, 23 suites). The fifth probe confirms an earlier reply completion clears newer unsent text in the same conversation. Component probes substitute network responses and sent no messages; the temporary checkout test was removed afterward.
- A fresh independent Python review reproduced **eight finding groups with negative controls** (A01/A02/A08/A09/A10/A12/A17/A18). It strengthened A02 with viewer-in-B/admin-in-A role controls, bounded A08 to delete-endpoint retry, checked ObjectId versus string-ID serialization, and confirmed changed voice bindings do not inherit an earlier approval. These probes overlap the findings above; their count is not added to a regression-test total. Two initial temporary harness expectation/role errors were corrected, with their logs retained. Final independent review approved this report and the three specification addenda; it is not implementation approval.
- Fresh GitHub reads now show normal CI `38094578259` **completed with backend failure and frontend-build success**, at test-only commit `648efd1`. Its retrieved log contains the three known auth/email test failures and stops during a long parameterized test output without a complete summary; this review does not infer a hang, timeout or the final failure count from that truncated evidence. Security CI `38094578266` remains failed. `main` is still unprotected and points to documentation commit `3fc64f7`.

Changes to the assessment and plan:

1. **Treat access lifetime as security work.** A15's missing membership recheck is P1 and moves into the first repair wave; its burst-loss/reconnect behavior remains P2. An already-open producer emitted a newly inserted task after actual membership deletion in native Mongo. This was a producer-level test, not an authenticated browser/socket lifecycle test.
2. **Fix both directions of A02.** A permission check must not authorize A while the handler writes B. Equally, a stale parent-router erasure check for closed B must not reject an otherwise permitted open A. The shared permission design must preserve final-tenant erasure admission, verified-email requirements, OAuth callback and public API-key bindings. It does not serialize all later revocations with every write.
3. **Bind draft revision as well as recipient.** A03 includes both cross-conversation text transfer and same-conversation loss of newer edits when an earlier request finishes.
4. **Do not assume the common importer is already atomic.** It supplies richer normalization, suppression and execution bindings, but reads campaign state and later inserts leads/updates counters separately. Reuse must harden that shared path too. The native A05 controls prepared zero jobs for current search/public admission and one job after supplying complete bindings in the same database. Missing sender/version/revision are concrete blockers; the scheduler has legacy fallbacks for root node and enrollment identity, so not every missing field independently prevents scheduling. No job was executed or published.
5. **Move small customer-trust fixes earlier.** A17 cancellation acknowledgement and A10 broken integration lists should follow the access/draft fixes without waiting for a large admission/deletion refactor.
6. **Keep operational incompleteness separate.** Restored execution activation, authenticated source completeness, live health observations, legacy migrations and IAM/egress/pilot evidence remain substantial unfinished work even after the UI/API bugs are fixed. Native and browser acceptance belongs to each repair wave, not only a final release phase.

Priority: **P0** repair immediately before expanding access; **P1** repair before the affected customer workflow/pilot; **P2** correct product truth or reliability before broader use. Priority does not imply a proven production exploit. No production data census was performed.

## Section-by-section result

| Section | Result | What remains |
|---|---|---|
| Home, navigation and header | Partial local repair | A15 access repaired in v2.57; A16 workspace/trial/billing uncertainty repaired in v2.58. Feed loss/resume remains A15 P2; A11 stored admission/checklist is repaired in v2.60. |
| Campaign list/detail and deletion/restore | Bounded local repair | A02 context repaired in v2.56; A08 stop-first journal/retry/paused restore repaired in v2.58. Older detached history is not reconstructed. A11 stored readiness is repaired in v2.60. |
| Campaign wizard, launch and scheduling | Bounded local readiness repair | A11 shared stored prerequisites and truthful/stale-safe checklist repaired v2.60. Final key/ownership/worker gates and operational proof remain. |
| Sequence canvas, templates and versions | Bounded checks pass | A01 strict prompt scope repaired in v2.56; DAG/tree/version contracts retained. Unsupported actions remain unavailable. |
| Leads list, export, notes and activity | Isolation repair retained | v2.55 scope plus v2.56 authorized context remain; no additional scope defect reproduced in current selected checks. |
| CSV, pasted URLs and staged-file intake | Bounded local admission repair | v2.58 shared transactional state/suppression/binding/counter/event contract; max 1,000 rows/request and held draft/paused rows. Older incomplete data needs migration. A04–A06. |
| LinkedIn/Sales Navigator search and staged review | Bounded local repair | Current active bindings, staged exclusions, warm-up denial, reviewed batching and truthful Stop/recovery are repaired in v2.58. No live crawler proof. A05–A07. |
| Sheets import and public lead API | Bounded local repair | v2.58 common admission and key/body-bound idempotency with native rollback/standalone controls. Older incomplete enrollments are not backfilled. A04–A05. |
| Inbox, replies, tags/snippets/reminders | Bounded local repair | A03 recipient/revision drafts and tab-session request recovery repaired in v2.58; exact approval/freshness/uncertainty controls retained. Two synthetic-API browser checks are not a live reply journey. |
| Engage lists, manual drafts and reports | Bounded local repair | v2.58 current cohort edit guards and generation-fenced projection/draft writes. Older orphan rows and abrupt-death running-state recovery remain separate. A06, A09. |
| Voice Studio and campaign voice preparation | Fix needed; rollout targets remain | Ambiguous/absent sender assignment still selects a voice. Consent/review/uncertainty retained; legacy/custody/live targets separate. A18. |
| Swipe files, writing styles and prompt tools | Bounded local repair | A01/curated prompt usage repaired v2.56; A19 failed analysis no longer saves generic styles, with guarded default insertion in v2.58. |
| Analytics, filters and CSV | A13 bounded local repair; A14 open | v2.61 recorded email acceptance/reference/possible/unknown evidence and scoped original-operation joins replace inferred delivery. LinkedIn acceptance/reply cohorts remain mismatched. |
| Live activity feed | Access repaired; delivery open | v2.57 current original-workspace access retained; burst loss/reconnect/durable coverage remains. A15 P2. |
| Settings: LinkedIn accounts/proxy | Bounded recovery repair; live proof outstanding | A12 eligible connection-only recovery and tenant-safe stops repaired v2.59. No task/campaign resume or execution grant. Fresh authentication/health/proxy/IAM/network proof remains separate. |
| Settings: Gmail/Microsoft mailboxes and Hunter | Bounded checks pass; live proof outstanding | Scoped/held custody and sync contracts retained; actual OAuth/scopes/cursor/send/reply/STOP journey unverified. |
| Settings: Content Review | Bounded checks pass | Exact revision/expiry/content/audio/RBAC retained. Explicit voice selection needed before preparing approval. A18. |
| Settings: Action Review | Bounded checks pass | Unknown outcomes remain held; human review is not provider receipt or automatic resume. Broader operator/native drills remain. |
| Settings: integrations, API keys, webhooks, Slack/CRM | Lists/intake repaired; activation unverified | A04/A05/A10 repaired locally v2.58. Real integration configuration/activation/end-to-end proof remains. |
| Settings: members/roles/invites | Bounded context repair | v2.56 same resolved role/workspace/deletion context retained. Actual invitation delivery not tested. |
| Settings: billing and Help | Bounded local repair | A16 loading/trial/paid truth and A17 exact-term cancellation acknowledgement repaired v2.58. No provider cancellation/IP-release proof. |
| Workers, suppression, custody, erasure and restore | Substantial guards; operational gaps | Current native contracts pass where selected. Authenticated restore/completeness/activation, legacy migrations and health/IAM/egress/pilot proof remain. |

“Bounded checks pass” means no additional confirmed defect was found in the inspected paths and selected tests. It does not mean the section is production-certified or exhaustively correct.

## Confirmed defects and repair criteria

### A01 — Prompt routes bypass workspace isolation (P0; fixed locally in v2.56)

Source: [prompt lead preview](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/prompts.py:205), [prompt library](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/prompts.py:100), [prompt deletion](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/prompts.py:168).

A member of current workspace A, without membership in former workspace B, can preview a B lead retained with their creator ID. The response includes real lead fields and all custom variables. The normal Leads activity route rejects the same record with 404; prompt preview returns 200. The prompt library also returns a foreign creator-tagged custom prompt, and deletion removes it with 200. This surviving path is outside the deployed Leads-router repair. Affected production-row population and exploitation are unknown.

Repair: apply strict scalar workspace scope to every customer lead/prompt read and mutation. Allow global visibility only through an explicit protected system-prompt contract; creator identity is not tenant authorization. Inventory other resource consumers rather than treating the Leads fix as global completion.

Acceptance: former members, foreign creator rows, UID aliases and missing/null/array scopes cannot preview/read/delete customer data; current members and protected system prompts behave correctly through actual permission dependencies and native Mongo query checks.

### A02 — Permission re-resolution and handler tenant can diverge (P1; fixed locally in v2.56)

Source: [workspace hydration](/Users/shubham/Documents/Workspace/SocialEntangler/app/api/deps.py:266), [permission re-resolution](/Users/shubham/Documents/Workspace/SocialEntangler/app/api/deps.py:501), [campaign deletion](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/campaigns.py:522), [team workspace context](/Users/shubham/Documents/Workspace/SocialEntangler/app/api/routes/team.py:107).

Authentication already hydrates the active workspace. Ignoring the permission dependency's returned copy is therefore not, by itself, proof of a broad ordinary revoked-member bypass. The reproduced case is narrower: identity initially resolves to B; membership in B is removed before the permission dependency runs; permission resolution falls back to valid workspace A, while the campaign handler retains B from the earlier identity. An offline HTTP probe using actual workspace hydration/permission code deleted a B campaign with 200 after authorizing A. The second native Mongo probe reproduced that race. Independently, a stronger role control gave the actor only viewer access in B and admin access in A: ordinary B deletion returned 403, but removal of B membership after initial hydration made the same request return 200 and delete B using A permission. No initial B membership returned 404; insufficient fallback-A permission returned 403. This requires the injected membership-change/fallback timing, not arbitrary tenant access. Authentication transport was substituted; the independent role controls used synthetic database storage.

Repair: consume one resolved tenant/actor permission context in handlers and erasure checks; bind resource writes to that context. Audit campaign, sequence, inbox, account, billing and team handlers for the same discarded-result pattern. A shared context alone is not a claim of universal transactional revocation serialization.

Acceptance: inject removal/workspace fallback between authentication and permission; no write reaches B. Test erasure holds on the final selected tenant, closed-old/open-new workspace fallback, role downgrade and unchanged valid-member behavior. Preserve verified-email checks for invitations and the separate OAuth callback/public-key authority paths.

### A03 — Inbox drafts transfer between recipients (P1) — bounded local repair in v2.58

Source: [thread selection](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/pages/OutreachInbox.js:448), [reply submission](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/pages/OutreachInbox.js:474).

A fresh component probe typed “Private Alice draft,” selected Bob, and clicked Send. The request went to `/inbox/b/reply` with Alice's text. The server uses the selected Bob thread; this is frontend draft/recipient misbinding within one workspace. The probe blocked queue submission and proves no real transmission. The second review also reproduced a delayed successful reply completion clearing newer unsent text in that same thread; the frontend checks thread identity but not the submitted draft revision.

Repair: key drafts by workspace/sender/channel/thread and capture draft revision with recipient at submission. Preserve newer edits when older jobs finish and retain exact failed/unknown content without suggesting blind resend.

Acceptance: Alice→Bob never transfers Alice's text; rapid switches and delayed completions cannot clear or send another thread's draft.

### A04 — Successful-row Sheets import crashes twice (P1) — bounded local repair in v2.58

Source: [Sheets UUID reference](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/integrations.py:678), [Sheets state reference](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/integrations.py:690).

With the integration pilot gate enabled only inside the synthetic test process, the first valid new row raises `NameError: uuid is not defined`. Supplying that missing binding temporarily reveals `AttributeError: LeadExecutionState has no attribute PENDING`. Neither probe inserts a row. Fixing only the first error is insufficient.

Repair: move Sheets through the common validated importer/admission path, including current campaign state, suppression, deduplication, row rejections, enrollment bindings and recoverable counters/events.

Acceptance: a valid row succeeds; duplicates, invalid URLs, suppressions, warm-up, active enrollment and interrupted retries behave consistently with the supported intake contract.

### A05 — Search/public enrollment reports success without runnable work (P1) — bounded local repair in v2.58

Source: [staged search commit](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/leads.py:595), [public enrollment](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/integrations.py:950), [common importer bindings](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/lead_importer.py:1025), [durable scheduler](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/tasks/sequence_dispatch.py:43).

Both current-handler probes returned success for an active campaign. The lead was queued without sender, node, immutable sequence version, enrollment identity or authorized revision. The actual scheduler prepared zero jobs with only its feature switch substituted to enable offline selection; no worker or provider ran. Ordinary shared CSV/URL admission already supplies active-campaign context. The second review added native database positive controls: after complete execution bindings were added, the same scheduler prepared one job for each source instead of zero. Root node and enrollment ID have legacy fallbacks; missing sender, version and authorization revision are the demonstrated blockers. Scheduler preparation is not dispatch authorization or a provider call.

Repair: centralize enrollment for every intake source, validating current campaign revision/status and assigning the necessary immutable execution context atomically or through a recoverable admission job. Do not loosen scheduler/dispatch checks to make incomplete rows run. The existing common importer also needs current-state ordering and recoverable inserts/counters; merely calling it from more routes does not supply those guarantees.

Acceptance: all supported sources produce valid runnable or explicitly held records; live-disabled behavior, concurrent pause/sequence changes, duplicate retries and partial counter/event failures are covered. Historical incomplete rows need a deliberate repair plan.

### A06 — Warm-up cohort mutations are inconsistently locked (P1 for the conditional feature) — bounded local repair in v2.58

Source: [staged search commit](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/leads.py:595), [armed-list guard](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/engage.py:90), [contact add](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/engage.py:435), [contact delete](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/engage.py:529).

Search commit accepts a `warming_up` campaign and changes staged rows to queued. Separately, deleting an armed Engage list returns 409, but adding/deleting contacts returns 200 while its campaign stays `warming_up`. Source-specific checks at job creation do not protect a later commit after campaign state changes.

Repair: enforce one current-state/cohort-revision boundary for all imports, staged commits and Engage contact mutations; invalidate/review any intended cohort change through the explicit arm/cancel workflow.

Acceptance: arm between crawl start and commit, or attempt contact add/delete while armed; deny or explicitly cancel/review without silently changing the captured cohort. Conditional auto-launch remains disabled by default; these probes do not demonstrate a live auto-launch bypass.

### A07 — Stop Crawl reports stopped after a rejected cancellation (P1) — bounded local repair in v2.58

Source: [crawl cancellation](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/components/ImportLeadsModal.js:252).

The component ignores HTTP success, marks the job stopped and stops its queued/crawling polling. A mocked 403 cancellation still produced “Search Extraction Paused,” removed Stop Crawl and displayed `stopped`; the server job was not cancelled.

Repair: acknowledge only successful cancellation, show cancelling/error/unknown states, and keep observing the real job until the server confirms a terminal status.

Acceptance: 403/409/500, network failure and delayed acknowledgement cannot display a confirmed stop or discard monitoring. Reopening the importer recovers the server job state.

### A08 — Interrupted campaign deletion cannot finish on retry (P1) — bounded local repair in v2.58

Source: [campaign deletion](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/campaigns.py:522).

Deletion writes the parent soft-delete before cancelling tasks, unassigning leads and deleting the sequence. Injecting a failure at task cancellation produced HTTP 500 with the campaign deleted, task still queued, lead still enrolled and sequence undeleted. Retrying the same delete endpoint returned 404 because normal lookup excludes the deleted parent. An explicit restore followed by delete is a separate available workflow, so the evidence establishes non-resumable deletion retries, not permanent unrecoverability. Existing dispatch guards still reject deleted campaigns; no continued-send bypass is claimed.

Repair: use a transaction where appropriate or a durable, idempotent deletion manifest with stop-first ordering and resumable cleanup. Restore must respect unfinished deletion and existing authorization holds.

Acceptance: fault after every step and lose each acknowledgement; retries finish the original cleanup without touching replacements, fabricating completion or reauthorizing outreach.

### A09 — Engage worker recreates a post after list deletion (P1) — bounded local repair in v2.58

Source: [late post projection](/Users/shubham/Documents/Workspace/SocialEntangler/app/celery_workers/tasks/engage.py:179).

The worker captures contacts, awaits a provider read, then upserts returned posts without a surviving list/contact revision fence. An isolated probe called the real list-delete handler during a fake read; afterward there were zero lists, zero contacts and one recreated orphan post. Readiness/physical-boundary and transport were substituted only to reach this post-response projection race. No actual request or dispatch bypass is claimed.

Repair: fence response projection against current list/contact ownership, generation and deletion in the same ordering protocol as deletion. A separate existence read alone leaves another race. Preserve any necessary outcome evidence independently of deleted customer content.

Acceptance: deletion during queued/running/read-received work never recreates posts, drafts or counters; legitimate saved outcomes can be retained/repaired without restoring deleted content.

### A10 — API-key/webhook lists fail on ordinary Mongo IDs (P1) — bounded local repair in v2.58

Source: [webhook list projection](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/integrations.py:160), [API-key list projection](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/integrations.py:323).

Both lists return raw rows without excluding `_id`; their creation paths permit Mongo-generated `ObjectId`. Actual FastAPI serialization with synthetic native IDs returns HTTP 500 for each populated list. This needs no database server to reproduce. Snippet/tag/style/swipe list paths correctly remove/exclude IDs and did not reproduce this error.

Repair: return explicit public response models/projections and exclude database IDs and private credential material.

Acceptance: empty and populated lists work with real BSON IDs, legacy/scoped custody metadata and strict secret-exclusion assertions through the actual HTTP response boundary.

### A11 — Preflight labels unavailable senders/proxies ready (P1) — bounded local repair in v2.60

Source: [shared readiness](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/campaign_readiness.py), [preflight and launch](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/campaigns.py).

A campaign with an “active” account, a configured proxy hostname and no usable session passed preflight with `can_launch=true` and “All assigned senders have verified proxies.” Live LinkedIn actions were disabled inside the probe. Launch rejected the same account; paid entitlement and the final sender-readiness result were substituted in the first probe to isolate the disagreement. A second native Mongo probe reproduced the same disagreement using actual entitlement and sender-readiness functions with synthetic paid rows and live actions disabled, without those substitutions. A hostname is configuration, not fresh health, lease or credential proof.

Verified local repair: stored GET and prospective POST preflight share known activation prerequisites with launch. Current flags/state/revision/resources/local material/restore/selected unresolved work and warm-up are checked without grants/provider probes. Missing saved sequences deny. Key preparation and repeated original-state reads precede the existing activation CAS. Known blocker parity/read-only/race/scope/overflow/email-only/native controls pass. The wizard renders actual fields and clears stale/failed checks, disables normal confirmation when unknown/blocked, and checks saved inputs again.

Execution checks remain explicitly pending/unknown: applicable recipient/revision approval, voice selection/artifacts, fresh permission, inbox/reply/suppression and health are final worker requirements, some dependent on the new allocation/revision. `can_launch` is advisory eligibility for final validation, never `execution_ready`. Scoped metadata is not ciphertext/key/IAM proof; sequential reads and activation are not an atomic cross-authority snapshot or restore activation. A13/A14, A15 P2, A18 and operational gates remain open. See [v2.60](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_CAMPAIGN_READINESS_RELEASE.md) for exact tests and limits.

### A12 — Resume relabels a disconnected sender active (P2; state-truth defect) — bounded local repair in v2.59

Source: [breaker resume](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/circuit_breaker.py:257).

A disconnected account with no cookie returned 200 and became active because resume checks existence/cooldown but not the eligible prior state/session. The reproduced account also lacks JSESSIONID, which the Voyager adapter rejects; launch and inbox have separate session checks, and default-off/permission controls remain. This does not prove the common physical guard verifies every possible malformed credential. The finding is false account state and incorrect recovery behavior, without a demonstrated provider call.

Repair: restrict breaker resume to eligible stopped/cooldown states; route disconnected/expired credentials through reconnection. Use conditional status/generation writes rather than an unconditional active transition.

Acceptance: disconnected, expired, replaced, review-held and erased senders cannot become active through the breaker endpoint; valid cooled-down senders remain stopped until their required checks pass.

Verified local repair: only recognized cooled-down checkpoints with usable encrypted material and current paid/proxy/ownership state can recover. The original account basis and selected authorities are revalidated under the guard transaction; fresh permissions/armed controls/selected unknown work deny. Force overrides are rejected. Response and native tests confirm no campaigns/tasks resume and no permission grant. Stored-material checks do not authenticate a fresh provider session. Adjacent stop helpers now enforce tenant scope. See v2.59 for evidence and limits.

### A13 — Analytics invents email delivery and mixes campaigns (P1) — bounded local repair in v2.61

Source: [email metrics](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/analytics.py:101).

One completed email task with no delivery receipt produced `delivered=1`, `deliverability_rate=100%`. Adding a bounce from another campaign in the same workspace changed the selected campaign to zero delivery. The query scopes bounces by workspace/time/sender, but not selected campaign or the corresponding sent operation.

Repair: distinguish submitted/provider-accepted/delivery-confirmed/bounced/unknown, join events to stable original operations, and apply consistent campaign/sender filters. Display unavailable delivery data as unknown rather than inferring success from silence.

Acceptance: provider acceptance alone never becomes delivery; foreign campaign bounces do not affect the selection; duplicate/out-of-order/older events retain original provenance and timestamps.

Verified local repair: [v2.61](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_EMAIL_EVIDENCE_REPORTING_RELEASE.md) counts supported stable scoped provider-accepted operations using original dates, excludes human provenance and treats legacy/contradictory projections separately. Recorded reference bounces join exact original operation/workspace/sender/time; conversation/address matches stay possible. No positive delivery/submission coverage is claimed. API, screen and CSV preserve unavailable/partial status; bounds and sequential fixed-as-of limits remain explicit. A14 is unchanged.

### A14 — Acceptance/reply rates mix unrelated cohorts (P2)

Source: [period event counts](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/analytics.py:92), [rate denominators](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/analytics.py:182).

One invitation/message sent in the period and two older leads accepting/replying in that period produced 200% acceptance and reply rates. Event-period counts can be useful, but dividing them by a different send cohort is misleading.

Repair: expose period activity counts separately from cohort conversion rates. Define the original denominator, attribution window and stable event time; do not merely cap the displayed percentage at 100.

Acceptance: old-cohort responses, repeated touches, delayed repairs, multiple senders and zero denominators produce explainable counts/rates, including exports.

### A15 — Live activity access locally repaired; event delivery remains open (P1 fixed locally; P2 open)

Source: [stream access and activity cursor](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/activity_stream.py:126), [Home activity handling](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/pages/OutreachHome.js:48).

Current local status: [v2.57 verification and limits](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_ACTIVITY_STREAM_ACCESS_RELEASE.md) repairs ongoing access with pinned scalar authorities, checks before reads/each emission, bounded generator lifetime, sanitized terminal controls and frontend cache clearing. Sequential checks retain a last-check-to-send race; blocked socket/proxy closure is not guaranteed. Reliable event delivery remains open.

Historical baseline evidence: eleven eligible completed tasks yielded ten task events; the next cycle was only a heartbeat. The newest-ten query advances to the current clock, permanently skipping the remaining event. There is no SSE event ID/resume contract; reconnect can repeat recent events. The producer scans task completion, despite broader activity claims, and the connection has no ongoing membership-revalidation loop. A fresh native database producer probe authenticated workspace membership, opened the generator, deleted the membership and inserted a new completed task; the same generator emitted that task. This is evidence of stale stream authorization, not a browser or production exploit demonstration. This access defect motivated the v2.57 repair; burst/reconnect correctness remains unfinished.

Remaining repair: page chronologically with a stable `(event_time, ID)` cursor, drain bursts, deduplicate and resume explicitly. Prefer the durable event surface if it can truthfully cover replies/acceptances/manual events.

Acceptance: bursts/tied times/reconnects do not silently lose or duplicate activity, and revoked membership ends access. Do not interpret a heartbeat as campaign health.

### A16 — Header, prompt usage and billing states fabricate certainty (P2) — bounded local repair in v2.58

Source: [header defaults](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/components/OutreachLayout.js:18), [trial rendering](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/components/OutreachLayout.js:151), [billing loading](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/pages/OutreachSettings.js:65).

The header still shows “Trial ends in 4 days” when the server says `trial_available=false`; workspace name/initials are placeholders. A separate component probe made billing return HTTP 503 and the page displayed “No paid sender access yet” without an error. Missing billing evidence is being shown as a confirmed unpaid state. The second source review also found five hardcoded prompt `runs_count` values (4,820 / 3,190 / 2,740 / 1,920 / 1,540) in [the default catalog](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/prompts.py:35), displayed as actual runs by [the prompt drawer](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/components/sequence/SequenceCanvas.js:2335). Those seeded values have no execution evidence; this added subcase is source-confirmed, not a new component probe.

Repair: load actual workspace/identity and authoritative subscription state; model loading, unknown, failed and confirmed inactive separately. Render a trial only when the server explicitly grants one and handle zero remaining days correctly. Remove invented prompt usage counts or replace them with a clearly defined measured value; a static curated catalog needs no usage claim.

Acceptance: active/inactive/pending/expired/cancelled/trial-unavailable/zero-day/error states agree across header, settings and readiness. Failed refresh must not replace a known entitlement with invented unpaid certainty.

### A17 — Cancellation acknowledges a lost conditional write (P1) — bounded local repair in v2.58

Source: [cancellation write](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/billing.py:134).

The cancellation update is conditional on the captured active term, but its match result is ignored. A probe renewed the term between read and write; the update matched nothing, yet the endpoint returned `cancellation_scheduled` with the old term and the current entitlement had no cancellation flag. This proves a local acknowledgement error, not a real charge/provider-renewal event.

Repair: confirm the exact cancellation transition and return conflict/reload on a lost compare-and-set, or implement an explicit request identity and durable current-term decision. Preserve the distinction between app cancellation and separately managed provider renewal.

Acceptance: renewal/revocation/concurrent cancellation/lost acknowledgement cannot return false success or cancel the wrong term. Retried confirmed cancellation remains idempotent.

### A18 — Voice selection is ambiguous and ignores unassignment (P2)

Source: [voice assignment](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/voice.py:144), [voice selection](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/content_approval.py:75).

Assigning a sender to another voice does not remove the earlier assignment. Binding selects the first unsorted assigned voice; if none are assigned it falls back to the first workspace voice. Independent production-binding probes selected the first vendor voice in both situations using valid synthetic consent/current-source metadata. Exact content/audio approval remains enforced; no consent bypass or unreviewed physical send was demonstrated.

Repair: require an explicit unique sender/campaign voice selection or an explicitly configured default. Reject ambiguous/missing assignments, invalidate affected prepared clips/reviews and preserve source/consent revisions.

Acceptance: two assigned voices are rejected or resolved explicitly; unassignment cannot silently choose another voice; selection is stable across ordering, edits and prepared-artifact recovery.

### A19 — Failed style analysis silently saves a generic persona (P2) — bounded local repair in v2.58

Source: [style fallback](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/styles.py:60).

A fake LLM failure returned a successfully saved style named after the user's sample, with generic instructions and no failure/fallback provenance. No model request was made. This does not establish the promised analysis of the supplied posts.

Repair: report analysis unavailable, or offer an explicit generic draft with visible provenance; persist pending/failed state if asynchronous analysis is introduced. Do not silently replace a default personalized style with an undisclosed fallback.

Acceptance: exception, empty result and valid analysis produce distinct truthful states; the user can retry without duplicate personas or unexpected default changes.

## Operational and release work still outstanding

1. **Security and CI.** v2.58 adds actual native/browser/component checks, a no-skip 144-case native gate, explicit async execution, outreach compilation/security coverage, compatible dependency updates and XML/private-temp controls. The fresh combined backend/build/component/browser runs pass. A fresh temporary Python environment has no known audit findings; scoped Bandit is clear. npm still reports 116 findings (69 high), Semgrep 35 warnings, and container/runtime exposure needs further review. Remote workflow execution and branch-protection enforcement are not verified. The earlier GitHub failures and unprotected-main observations below describe 11 October; no new remote claim is made. Legacy mocks still isolate historical tests, and omitted opt-in/crash drills are not inferred from passing unit tests.
2. **Authenticated journey and integration activation.** Verify real login/workspace/roles, imports, explicit approval, paused/disabled behavior, queue recovery, mailbox reconnect/catch-up, inbound reply stops, integrations and deletion under controlled conditions. Separate recorded manual work from provider acceptance and delivery. Existing deployment health is not this evidence.
3. **Health and worker operation.** The current health control consumes original connection evidence with a 90-second validity window; the control window alone does not refresh observations. Implement bounded, charged observations and explicit cohort controls. Measure inbox age, queue wait, publication lag, unknown outcomes, repair backlog and suppression contention before deciding worker/process capacity. Queue names alone do not establish isolation.
4. **Backup recovery and safe reactivation.** v2.51–v2.54 remain offline metadata/signature/input validators. They do not authenticate outside-backup payment/provider/resource facts, prove completeness, recover unproven reply mappings/suppressions or perform transactional activation. The installed positive restore gate deliberately refuses restored execution. Finish those contracts and rehearse them against an isolated real replica set/actual backups, including conflicting writes and uncertain outcomes; no automatic campaign resume.
5. **Legacy migration and live controls.** Census remaining shared/provider secrets, missing-original-fact Webshare cases, older/unproven voice inputs/artifacts and different-key lineage. Unproven data stays held. Verify actual deployed IAM, kernel/network restrictions and a bounded explicitly authorized pilot. Preserve the documented access-route decision before enabling private-endpoint traffic. No new policy or provider approval is claimed by this audit.

Relevant evidence: [CI workflow](/Users/shubham/Documents/Workspace/SocialEntangler/app/.github/workflows/ci.yml:27), [legacy test substitutions](/Users/shubham/Documents/Workspace/SocialEntangler/app/tests/conftest.py:16), [passive health controls](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/health_monitor.py:24), [corrected recovery scope](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_RESTORE_HELPERS_REVERIFICATION.md:5), [restore positive gate](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/restore_epoch.py:132), [v2.55 deployment and repair evidence](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_LEAD_WORKSPACE_ISOLATION_RELEASE.md:1).

## Recommended repair order

| Wave | Changes | Required exit evidence |
|---|---|---|
| 1 | A01/A02 v2.56 and A15 access v2.57 repaired; v2.58 adds CI/security foundations | Native/browser contracts pass locally; remaining npm/Semgrep/container and remote required-check enforcement stay release gates. |
| 2 | A03/A17/A10 repaired locally in v2.58 | Recipient/revision/unknown recovery, exact-term cancellation and BSON/secret exclusion checks pass. Live messaging/provider cancellation remains unverified. |
| 3 | A04–A07 repaired for participating current paths in v2.58 | Shared ordered intake/warm-up/cancel contracts pass natively; census/migrate older incomplete enrollments and verify live crawler separately. |
| 4 | A08/A09 repaired for current lifecycle/projection paths in v2.58 | Native phase faults, simulated commit-response loss and generation replacement controls pass. Older detached/orphan history and abrupt-death recovery remain separate. |
| 5 | Next: A14 cohort rates, A15 P2 feed, A18 voice | A13 email evidence repaired v2.61, A11 admission/checklist v2.60 and A12 recovery v2.59. Remaining work needs coherent LinkedIn conversion cohorts, ordered feed recovery and explicit voice provenance. |
| 6 | Authenticated recovery/activation, remaining migrations, charged health, IAM/egress/pilot, release | Current local checks do not prove source-authenticated completeness, activation or actual live controls. Complete those contracts and authorize the release before rollout. |

Avoid a framework/database rewrite or more metadata-only “completion” slices. Fix the customer paths against the existing conservative execution contracts, then prove the operational workflows. Refactor duplicated admission/readiness/API-client logic while repairing it; preserve stable identities, existing receipts, unknown outcomes and stop-on-reply controls.

After correctness, measure analytics query cost (the 30-day chart performs 180 daily counts plus summaries), add bounded pagination where lists cap silently, centralize visible loading/error/job states, and run an authenticated accessibility/mobile review. These are improvements, not additional reproduced security failures.

## Evidence locations

Current v2.60 evidence: `/tmp/unravler-readiness-20261012/` contains final combined/native XML, coverage, frontend/build/browser and scoped scan results. See the v2.60 report for current counts and limits. Earlier v2.58 implementation evidence: `/tmp/unravler-next-fixes-20261012/` contains combined/backend XML, native no-skip XML, frontend/build/Chromium logs, dependency/static scan results, coverage, protected pre-edit backups and final verification metadata. See the v2.58 release for that checkpoint; v2.59 evidence is in `/tmp/unravler-readiness-resume-20261012/` and its report. Earlier evidence below describes audits or prior releases.

Second-review evidence: `/tmp/unravler-section-recheck-20261011/` contains the rerun backend probes, 13-case native diagnostic module/log (and retained initial fixture-error log), five component probes/frontend log, source fingerprint comparison and fresh GitHub metadata/logs. The owned Mongo process and temporary frontend test were removed; application source and operational configuration remain unchanged.

Parent first-pass evidence: `/tmp/unravler-section-audit-20261011/` contains `backend-probes.json`, `backend_probes.py`, `route-inventory.json`, `frontend-probes.log`, `SectionAuditProbe.test.js`, `guards-regression.log` and `native-scope.log`. First regression log: `/tmp/unravler-section-audit-backend.log`; frontend baseline log: `/tmp/unravler-section-audit-frontend.log`.

Second independent review: `/tmp/unravler-python-audit-challenge-0ycHVr/` contains `challenge.py`, `challenge.log` and `challenge-results.json`, with eight diagnostic groups and their negative controls. The cancellation probe reproduces a known zero-match conditional write, not a simulated lost network/storage acknowledgement.

First independent evidence: `/var/folders/v_/hqdkw39d5yg6d_8gk__sjdmm0000gn/T/unravler-backend-audit-e276mpl9/probes.json` and `probes-extra.json`. The initial contact-delete probe lacked a fake database method; the corrected extra probe is the evidence for its 200 result. No production resources were used.

GitHub observations: [normal CI](https://github.com/shubhamvivek234/app/actions/runs/38094578259), [security CI](https://github.com/shubhamvivek234/app/actions/runs/38094578266). These are observations at inspection time, not a promise about later run status.

Temporary paths may be cleaned by the operating system. The report records source locations, exact reproduction outcomes, limits and repair criteria so the findings do not depend on those paths surviving.
