# Unravler outreach audit — 10 October 2026

Reviewed application: `e506747cc25f2dd400250c7a8af0b60037a449a3`; checkout `cc01f4477765cc27a8205dfeec0d38c301f63756` adds documentation only.

## Assessment

Keep the existing FastAPI, MongoDB, Celery and React architecture. The durable execution and recovery controls are substantial. The next work should make the ordinary customer journey correct, make readiness and reporting truthful, and establish enforceable release checks.

This review found nine concrete defect groups, including a workspace authorization gap affecting retained legacy leads. Several everyday import/enrollment paths are broken or report success without producing runnable work. These should take priority over adding sequence actions or another metadata-only recovery helper.

The deployed application remains a gated pilot. Deployment health, passing unit tests and the presence of recovery modules do not establish live outreach readiness or complete disaster recovery.

Follow-up, 11 October 2026: **F1 is fixed locally in v2.55**, including verified workspace context, scalar tenant scope and subsidiary importer writes. See the [repair and verification report](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_LEAD_WORKSPACE_ISOLATION_RELEASE.md). It is not deployed. F2–F9 and the operational recommendations remain pending. The findings and read-only evidence below describe the audited baseline, before this repair.

## Scope and evidence limits

- Read current session memory, the three architecture baselines, release evidence, outreach APIs/core/worker paths, frontend screens and existing tests. Reviewed key customer flows and their boundaries; this is not a proof that every branch of all 146 Python modules and 46 frontend JavaScript files is correct.
- Independently reviewed backend tenant access, enrollment and integration paths. Rechecked the frontend draft/trial findings independently against source.
- Fresh verification: **261 existing backend tests passed** across 15 selected modules; **99 existing frontend tests passed** across 22 suites. Independent backend reviewer completed **a separate 70-test focused run**; this is not added to the parent total.
- Two temporary frontend component probes reproduced the draft and trial defects. Synthetic backend handler/generator probes reproduced delivery, cohort, readiness and activity-feed defects. Independent backend probes reproduced the tenant, Sheets and enrollment defects. These are reproductions of incorrect current behavior, not passing acceptance tests for a fix.
- Outreach-only Bandit at medium/high severity and confidence reported no findings. Its totals contain 11 low-severity findings. Static scanning did not detect the semantic defects below. Optional lint/type tools were unavailable in the independent review environment.
- No authenticated browser journey, production data inspection, real provider action, AWS permission/network test, database restore, native MongoDB race suite or Redis crash drill was performed during this audit. Earlier real-database/crash/build evidence remains historical and is described in the release reports.
- Application code and production configuration were not changed. Temporary component probes were removed; evidence logs remain in temporary storage. The audit document and session record are the only intended local changes.

Priority: **P0** correct immediately or block expansion/affected activation; **P1** correct before a controlled customer pilot; **P2** improve before broader scale. Priority reflects product impact, not an assertion that each issue is a critical security vulnerability.

## Confirmed defects

| ID | Priority | Finding | Consequence |
|---|---|---|---|
| F1 | P0 | Lead access accepts creator identity across workspace boundaries | A removed member can read/change retained foreign-workspace legacy leads |
| F2 | P1 | One inbox draft is shared across conversations | A draft written for Alice can be submitted to Bob |
| F3 | P1 | Sheets import has two deterministic runtime errors | A valid new row fails instead of importing |
| F4 | P1 | Search commit/public enrollment omit execution bindings | An active campaign reports enrollment but prepares no work for the new lead |
| F5 | P1 | Preflight and actual execution readiness disagree | UI can report ready while launch is disabled; host presence is labeled proxy health |
| F6 | P1 | Email delivery is inferred from sends minus bounces | UI invents delivery evidence and mixes other campaigns' bounces |
| F7 | P2 | Acceptance/reply rates use different event cohorts | Reported rates can exceed 100% and shift after repair |
| F8 | P2 | Activity stream truncates then advances its cursor | Busy intervals lose events; reconnects can repeat recent events |
| F9 | P2 | Header fabricates a four-day trial | Billing and onboarding contradict the managed paid pilot |

### F1 — Enforce workspace authorization consistently

Evidence: [lead campaign filter](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/leads.py:52), [list/export scope](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/leads.py:649), [pause mutation](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/leads.py:1197).

The filters allow `workspace_id == active workspace OR workspace_id == user_id OR user_id == current user`. Creation identity therefore remains an authorization path even when the record explicitly belongs to another workspace.

Independent offline reproduction: a user authorized for their personal workspace A, without membership in former team workspace B, could list a creator-tagged legacy B lead including its email, pause that lead, and pass the lead API's campaign lookup for their B campaign. Permissions were checked for A. Modern lead models omit `user_id`, so the demonstrated lead exposure concerns retained legacy creator-tagged rows; modern campaign records still have creator identity. There is no evidence from this audit that production contains such exposed rows or that exploitation occurred.

**Change:** use one strict active-workspace resource scope across list, export, detail, notes, stage, pause/resume, delete and campaign lookup. Handle legacy ownership through an explicit, proven migration, retaining ambiguity for review. Do not preserve a creator bypass for convenience. Audit subsidiary updates that use only a lead/campaign/job ID.

**Acceptance:** former members, active members of a different workspace, creator-tagged foreign records, and missing/unproven legacy scope all fail appropriately. Test both read and mutation routes with actual permission dependencies. Valid current members retain access.

### F2 — Bind reply drafts to the selected conversation

Evidence: [thread selection](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/pages/OutreachInbox.js:446), [reply submission](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/pages/OutreachInbox.js:471), [composer](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/pages/OutreachInbox.js:1057).

`replyText` is global page state. Switching threads does not save, clear or rebind it. A component probe typed a private draft for Alice, selected Bob, and observed that clicking send posted the Alice text to `/inbox/b/reply`.

This is frontend content misbinding within the user's workspace. The server correctly binds the request to the selected Bob thread; this finding is not a server routing or cross-tenant defect. Queueing does not prove transmission, which still requires the worker gates and permission.

**Change:** keep drafts keyed by workspace/sender/channel/thread, or require explicit discard on switch. Capture draft revision and recipient together when submitting. Preserve newer edits after an earlier job finishes. Show the recipient clearly and track pending jobs across navigation/reload.

**Acceptance:** switching Alice→Bob never transfers Alice's draft; delayed responses cannot clear Bob's draft; a failed/unknown job retains its exact content and review status without inviting blind resend.

### F3 — Repair Sheets ingestion through the common importer

Evidence: [missing UUID binding](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/integrations.py:678), [nonexistent state](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/integrations.py:690).

The first valid, unsuppressed, nonduplicate row raises `NameError: uuid is not defined`. A second isolated probe supplying that import reaches `AttributeError: LeadExecutionState has no attribute PENDING`. No rows were inserted in either probe. Existing tests do not exercise this successful-row path adequately.

**Change:** fix both errors and route Sheets rows through shared normalization, suppression, deduplication and enrollment logic. Define partial-batch results and idempotent retries, rather than letting a late error turn an imported prefix into an unexplained failure.

**Acceptance:** at least one valid row imports through the actual handler; duplicate, suppressed and malformed rows produce explicit outcomes; active-campaign bindings match the same contract used by CSV/URL ingestion.

### F4 — Make enrollment mean executable enrollment

Evidence: [staged commit](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/leads.py:610), [public enrollment](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/integrations.py:952), [scheduler requirements](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/tasks/sequence_dispatch.py:64), [shared importer](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/lead_importer.py:850).

Search-generated staged leads committed into an already active campaign become `queued` without the sender, immutable sequence and authorization bindings needed by the scheduler. Public API enrollment similarly creates an incomplete queued record. Independent actual-handler probes returned `enrolled_count=1` or `status=enrolled`, then the scheduler prepared zero jobs. The ordinary shared CSV/URL importer already supplies active-campaign context.

**Change:** centralize enrollment for all intake routes. Choose and implement an explicit policy for adding leads to active campaigns: a complete current authorization snapshot, or a visible held state requiring review/relaunch. Revalidate campaign revision during admission. Inspect existing incomplete rows and repair only with current, explicit authorization.

**Acceptance:** every intake path produces the required binding or a clearly labeled held result. Tests run actual intake through `prepare_due`; pause/sequence-edit/reply/duplicate races cannot accidentally authorize work. Repairing old rows must not silently resume stopped work.

### F5 — Use one readiness vocabulary across UI, launch and workers

Evidence: [preflight supported-only check](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/campaigns.py:736), [proxy label/check](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/campaigns.py:782), [ready result](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/campaigns.py:899), [launch disabled-step rejection](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/campaigns.py:1168).

A synthetic campaign with a paid term, lead, supported sequence and active sender returned `can_launch=true` while `OUTREACH_LIVE_ACTIONS_ENABLED=false`. A synthetic hostname alone produced “All assigned senders have verified proxies.” The checklist tests support but not `live_enabled`, and its host check establishes configuration presence rather than current proxy health/ownership/term. It also gives a stronger all-outcomes-reconciled label than its narrow task-state check proves.

This is a false-readiness defect, not a demonstrated bypass of final launch/transport guards.

**Change:** return separate facts for draft validity, deployment capability, paid access, sender/asset proof, current health, inbox coverage, content approvals, execution permission, unresolved outcomes and restore holds. Include reason codes, evidence timestamps and a link/action for each blocker. Keep final dispatch checks authoritative; a UI preflight snapshot must never become a durable grant.

**Acceptance:** disabled steps, stale inbox/health, expired assets, absent permission, stopped restore authority and unknown outcomes appear accurately. Configure-only checks never say “verified healthy.” A valid draft can remain editable while execution is blocked.

### F6 — Stop presenting inferred email delivery as verified delivery

Evidence: [email calculation](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/analytics.py:102), [delivery card](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/pages/OutreachAnalytics.js:347).

The API calculates `delivered = sent - bounce_count`. Two completed email tasks with no delivery evidence yielded two delivered/100%. Adding one bounce belonging to a different campaign in the same workspace changed the selected campaign to one delivered/50%, because the bounce query omits campaign identity. Absence of a recorded bounce cannot prove inbox delivery.

**Change:** separate accepted/sent, observed bounce, provider-confirmed delivery where actually available, reply and unknown. Return unavailable delivery when no supported evidence contract exists. Attribute bounce evidence to the original operation/message/campaign and deduplicate it.

**Acceptance:** no delivery evidence means unavailable delivery, not 100%; another campaign's bounce cannot affect the selected campaign; duplicated or late events do not fabricate outcomes.

### F7 — Make rates cohort-based and use immutable event time

Evidence: [window counts](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/analytics.py:88), [rates](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/analytics.py:174).

Tasks completed/updated in the selected window are the denominator, while leads accepted/replied in the window are the numerator. Replies to earlier messages and pre-existing connections can therefore exceed current-window sends. An offline example produced 300% from one message and three replied leads. Repairs can also move task `updated_at`, changing historical send buckets.

**Change:** retain independent event counts, but compute conversion rates from the same enrollment/invitation cohort and observation window. Use immutable original acceptance/send timestamps and preserve provider-observed versus human-attested provenance. State how pending cohorts and late replies are handled.

**Acceptance:** campaign/sender filters and numerator/denominator identities agree; late replies and projection repairs preserve the original send date; rates are either valid cohort measurements or explicitly unavailable.

### F8 — Give the activity feed a durable, resumable cursor

Evidence: [newest ten rows](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/analytics.py:291), [cursor advancement](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/analytics.py:312), [home feed copy](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/pages/OutreachHome.js:256).

The stream reads the newest ten completed tasks and then advances `last_check` to now. A generator probe with 11 eligible tasks emitted ten and no remaining task in the next cycle. Reconnect starts another ten-minute window, while the frontend prepends without event deduplication. The feed also promises accepted invitations/replies although this producer only scans completed tasks.

**Change:** consume an appropriate durable event source with stable ordering and `(event_time, event_id)` continuation; drain a page before advancing beyond it. Support resume IDs and frontend deduplication. Recheck long-lived stream authorization when membership changes. Name the event types actually emitted and bound connection/retention costs.

**Acceptance:** bursts beyond one page, equal timestamps, reconnects and membership revocation neither lose authorized events nor expose further unauthorized events. Inbox/reply and manual-action events use their original provenance.

### F9 — Show actual workspace and commercial state

Evidence: [default trial](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/components/OutreachLayout.js:18), [truthy-only update](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/components/OutreachLayout.js:39), [trial pill](/Users/shubham/Documents/Workspace/SocialEntangler/app/frontend/src/outreach/components/OutreachLayout.js:151), [billing contract](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/api/billing.py:66).

The header initializes four days, receives `trial_available=false` with no remaining-days field, and still renders “Trial ends in 4 days.” A component probe confirms this. Workspace name and initials are also fixed placeholders rather than loaded identity. This is a display defect, not an entitlement bypass.

**Change:** display request/quote/payment/paid-through/cancel-at-end state from the authoritative billing response. Load actual workspace/profile identity. Make onboarding check entitlement, sender verification, approved content and launch eligibility, rather than treating any saved campaign as completed setup. Show capability and role restrictions before the user attempts an unavailable action.

**Acceptance:** no trial appears when retired; zero/null/error states do not fall back to invented facts; workspace identity matches the active workspace; unavailable actions explain their blocker.

## Operational and architecture improvements

### R1 — Make a passing release enforceable (P0)

The application commit's [security workflow](https://github.com/shubhamvivek234/app/actions/runs/38050731122) remains failed. Recorded CI results include 72 Python vulnerabilities across seven packages (PyMongo, cryptography, Pillow, Sentry SDK, pytest, requests and Starlette), 136 NPM findings including three critical, existing wider Bandit findings and a libxml2 container finding without a fixed package version listed by that scan. These counts describe the CI-resolved dependency stack; they are not a reachability assessment or 72 proven exploitable outreach paths. PyJWT was already updated to 2.15.1 during deployment.

GitHub reports `main` **unprotected** at this audit. The [frontend build](https://github.com/shubhamvivek234/app/actions/runs/38050731115/job/114209586032) passed; the full backend job remained in progress at inspection. Vercel auto-deploys from main, so this rollout demonstrated that deployments can occur while security checks are red.

Triage runtime-reachable findings first, update compatible dependency groups with regression checks, and record narrow, expiring exceptions where no fix exists. Require reviewed changes and named checks before production promotion. Keep the ability to ship an explicitly approved emergency correction, with a recorded reason. Do not apply blanket audit fixes or turn a failing scanner into a passing check by ignoring its findings.

### R2 — Promote real integration checks into CI (P1)

Evidence: [current CI](/Users/shubham/Documents/Workspace/SocialEntangler/app/.github/workflows/ci.yml:14), [legacy test isolation](/Users/shubham/Documents/Workspace/SocialEntangler/app/tests/conftest.py:17), [opt-in native ordering tests](/Users/shubham/Documents/Workspace/SocialEntangler/app/tests/test_outreach_dispatch_authority.py:27).

The current frontend job builds but does not run the outreach component suite. The syntax command omits `outreach/`. Several important real-Mongo tests are opt-in, while broad legacy fixtures replace transaction, suppression, erasure and restore checks. Those fakes serve useful unit-test purposes but cannot establish their production guarantees. The existing “e2e regression” file primarily calls handlers with mocks; it does not cover the authenticated browser-to-worker journey.

Add separate, visible jobs for unit tests, frontend tests, a disposable Mongo replica set, standalone denial, Redis/loopback crash cases and an isolated browser journey. Restrict test network access to stand-ins and fail if critical integration jobs are skipped. Add the exact cases F1–F9, API dependency enforcement and all intake routes. Bound durations and publish failure artifacts. Both production Dockerfiles and CI use Python 3.11; the fresh local audit ran Python 3.12, so CI remains necessary for deployed-runtime confirmation.

### R3 — Finish operational activation and visibility (P1, before live execution)

Evidence: [passive monitor](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/health_monitor.py:23), [original connection evidence](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/health_monitor.py:61), [shared worker queues](/Users/shubham/Documents/Workspace/SocialEntangler/app/docker-compose.prod.yml:273), [bridge network](/Users/shubham/Documents/Workspace/SocialEntangler/app/docker-compose.prod.yml:357).

The health monitor consumes original verified connection evidence with a 90-second freshness limit. It does not itself collect new live observations; source search found the production evidence writer in connection verification. A 15-minute control window therefore does not establish 15 minutes of refreshed health. Design bounded, charged observations and explicit cohort authorization before claiming continuous health-based execution.

Outreach control, sync and dispatch share the outreach queue, and its worker also consumes unrelated publishing queues. On the small host recorded during deployment, resource pressure already affected startup. Measure queue wait, inbox coverage age and suppression-guard contention, then reserve execution/control capacity and isolate workloads as needed. A queue name alone does not create process isolation; [Celery documents explicit worker queue selection](https://docs.celeryq.dev/en/stable/userguide/routing.html).

Generic application metrics/Sentry exist. Add outreach-specific alerts for stale inbox coverage, oldest due job, unknown physical outcomes, held credentials, publication lag, expired terms, rejected permissions and recovery backlog. Show a single “why this campaign is blocked” view with corrective actions. Present observed state separately from the operator's desired active state.

Application proxy checks are valuable, but the checked Compose configuration uses a normal bridge network and does not demonstrate kernel default-deny egress or deployed workload IAM. Verify actual policy and negative paths under controlled conditions before enabling the pilot; do not infer them from code guards or successful health endpoints. The pre-existing integration flag being true is not evidence that all integrations are activated or verified.

### R4 — Complete recovery as an operational capability (P1, before promising recovery)

Evidence: [selected metadata comparison](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/restore_reconciliation.py:1), [offline activation review](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/restore_activation.py:157), [reply metadata validation](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/restore_reply_evidence.py:61), [positive gate](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/core/restore_epoch.py:132).

v2.51–v2.54 remain offline validators. They do not authenticate payment/provider facts, prove source completeness, restore actual sender-bound reply suppression or perform a transactional activation rehearsal. `restore_epoch.positive` deliberately holds restored execution. This refusal is a useful safety control, but the customer recovery workflow remains unfinished.

Implement authenticated outside-backup facts and bounded completeness manifests; prove sender/recipient mappings and restore suppressions; design an exact new-epoch transactional activation with durable approval/receipt and no automatic campaign resume. Rehearse using an isolated real replica set, restoring actual backups and injecting conflicting writes/unknown outcomes. Record achieved recovery time/data loss and unrecoverable obligations. MongoDB's [transaction documentation](https://www.mongodb.com/docs/manual/core/transactions/) is relevant to the database boundary; dictionary validation is not that boundary.

Remaining legacy credential/proxy/voice cases need a resource census, explicit supported migration contracts and a held state for unproven data. Inventory completion and source signatures must never be substituted for provider ownership, revocation or delivery proof.

### R5 — Resolve the LinkedIn access route before live expansion (P0 for affected execution)

Evidence: [private-endpoint adapter](/Users/shubham/Documents/Workspace/SocialEntangler/app/outreach/engine/voyager_client.py:1) and the architecture's access boundary.

The app depends on private LinkedIn endpoints. LinkedIn's [published policy](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibited-software-and-extensions) prohibits unauthorized automation/scraping and describes restriction and interruption risks. Dedicated proxies, rate limits and user consent do not establish platform authorization.

Record the supported access route and product decision for each live action before enabling it. Preserve useful permitted imports, drafts, approvals, manual engagement and reporting as independent workflows. Keep provider parsing replaceable and test schema drift with recorded contracts and bounded authorized checks.

## Product and maintainability priorities after the defects

- **Operator usability:** unify content review, action review, connection holds and resource repair into a navigable work queue. Expose exact outcome/provenance and the safe next step, without showing secrets or suggesting replay of uncertain actions.
- **Lead quality:** preview normalization, dedup scope, missing variables and suppression outcomes consistently across CSV, search, Sheets and public API. Preserve origin and row-level rejection reasons. Measure import-to-approved-enrollment success.
- **Analytics performance:** the 30-day chart issues 180 daily count operations plus summary queries per request. Replace repetitive round trips with bounded grouped aggregates or measured projections, keeping original event provenance. Profile query plans before increasing database/worker capacity.
- **Frontend consistency:** share authenticated request/error handling, capability/role context and background-job status components. Standardize cancellation/stale-response handling, keyboard focus, dialogs, responsive layouts and accessible controls. These are code-level recommendations; a full visual/accessibility audit with authenticated browser sessions remains to be done.
- **Module boundaries:** campaign/leads/integration handlers and several React screens are large and duplicate enrollment/readiness/fetch behavior. Extract cohesive admission, reporting and API-client services around stable contracts as fixes land. Preserve UUIDs, existing authorities and historical uncertainty; a framework or database rewrite is not justified by this review.
- **Documentation:** create one current capability/evidence register linking code, tests, enabled environment and live verification. Archive the long slice-by-slice appendices as history. Repeated “local complete” entries currently make it difficult to distinguish built, deployed, enabled and operationally proven.

## Recommended implementation order

| Wave | Work | Exit criterion |
|---|---|---|
| 1 | F1 strict tenant scope; runtime security triage and release checks | Revoked/foreign membership tests pass; reviewed release policy and vulnerability disposition recorded |
| 2 | F2 draft identity; F3/F4 common ingestion and enrollment | Every intake route reaches valid held/runnable state; switching threads cannot transfer drafts |
| 3 | F5/F6/F7/F9 truthful readiness, billing and reporting; F8 event cursor | UI blockers agree with current capabilities; no fabricated delivery/trial/cohort rate; stream drains/reconnects correctly |
| 4 | Native CI/browser journey, operator visibility and measured worker capacity | Critical real-boundary checks run without skips; a complete controlled user journey is demonstrated |
| 5 | Authenticated recovery/activation, remaining custody, IAM/egress and bounded pilot | Actual restore/activation and negative network/permission drills pass; explicit access route/cohort approval and pilot evidence recorded |

Keep live outreach disabled while the relevant release criteria are unmet. Existing automated checks and conservative execution controls should be retained throughout these changes.

## Evidence artifacts

- [Deployment and wider security observations](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_V2_54_DEPLOYMENT.md).
- [Corrected restore-helper scope](/Users/shubham/Documents/Workspace/SocialEntangler/app/docs/UNRAVLER_IO_RESTORE_HELPERS_REVERIFICATION.md).
- Backend audit probes: `/var/folders/v_/hqdkw39d5yg6d_8gk__sjdmm0000gn/T/unravler-outreach-audit-o7tl1ch4/backend-probes.json`.
- Frontend audit probes: `/var/folders/v_/hqdkw39d5yg6d_8gk__sjdmm0000gn/T/unravler-outreach-audit-xew80zfs/frontend-probes.log`.
- Outreach Bandit report: `/tmp/unravler-outreach-audit-bandit.json`.

Temporary paths are session evidence and may be removed by the operating system. The findings, exact source references, probe inputs/outcomes and acceptance criteria are recorded above so the plan does not depend on those files surviving.
