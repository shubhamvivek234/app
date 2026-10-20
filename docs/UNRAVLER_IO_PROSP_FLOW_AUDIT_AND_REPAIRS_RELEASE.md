# Unravler.io v2.95 — Lead, sequence, sender and launch audit

Date: 2026-10-20 (IST). Scope: authenticated Prosp comparison and bounded local repairs. Application changes are local; no commit, deployment, live activation or production migration was performed.

## Evidence boundary

The signed-in Prosp workspace was inspected in the user's Ulaa browser: Home, Leads and its import dialog, new-campaign setup, template gallery and sequence preview, Settings and both sender-connection forms. It had zero connected senders and no active trial. Both Basic LinkedIn search and CSV imports stopped at **Connect LinkedIn first**. Attempting to create the clearly named audit draft returned **Start your trial in Settings → Billing to run campaigns**. No successful draft, imported contacts, connected sender, trial, charge or outreach was created. Paid editor, extraction results and physical launch execution remain unverified.

Authenticated UI inspection used the browser extension. That browser did not expose the loopback CDP endpoint used by REA; its credentials were not copied to a different browser. REA separately captured the public/login pages and analyzed JavaScript downloaded from exact asset URLs observed on the authenticated routes. The downloaded bytes are hashed, but were not reconciled against debugger-captured bytes in the authenticated browser. Static client evidence does not reveal Prosp's private backend code, queue topology, database, permission implementation or successful execution.

Final retained REA summary: `ev_a4b8b94d19d7df1f116cb6bdb0f0bd084cfb3302375c46bd111183b80974bb72`, parent `ev_3c77df2e5d5878389644332b9204069a9bc445d7800a3a39c5387ce2a1af1d4e`. Four selected assets contain 141,078 bytes, all four parse, with zero parse failures. Semantic/application graph coverage is partial, including resource-limited graph expansion; missing facts are unknown. Focused module views: sender `ev_99d529d8813ada575ea8cfdcbd5dbf87ab92970a2f086fffb93fefcd2017478e`, imports `ev_e11537efcb5e0a67ac1a0f824d0184b354e8285bec237f54da7602af4ec8b75f`. Inputs, SHA-256 values, summary and focused views are retained in `/tmp/unravler-flow-audit-RX116d`. A prior REA session ended during the usage interruption; its later empty export is not evidence of a complete retained bundle. The final summary/views were saved separately after reanalysis of the preserved asset bytes.

Older local Prosp reports are background, not a verified current implementation specification. In particular, marketing assertions, videos and shipped UI do not establish backend architecture, account safety, conversion rates or working collectors.

## Comparison of the actual flow

| Section | Observed Prosp behavior | Verified Unravler state and action |
| --- | --- | --- |
| Lead sources | Five visible choices: Basic LinkedIn search, Sales Navigator search, My network, LinkedIn post, CSV. | Public-profile and CSV intake work locally. Basic/Sales Navigator collection, post engagement collection, network extraction and a provider-backed B2B finder are not active working sources. Parser support alone never enables collection. |
| Lead organization | Named lists, all contacts, status/source/location filters, configurable columns, search and export controls. | Workspace lists, reviewed membership/imports, lead selection, tags, exclusion and campaign assignment exist. Source/location filtering and richer configurable columns remain follow-up product work. |
| CSV intake | UI is visible but blocked until a sender is connected. Later mapping and successful import were not exercised. | Fixed required-name preview/commit parity, missing-name correction, location preservation, invalid-row totals, exclusion parity and canonical deduplication. Unpaid draft intake remains available. |
| Campaign setup | Named draft from scratch or template; this workspace's create request is trial-gated. | Drafts and sequences can be prepared before live entitlement. Fixed concurrent draft-save/launch races and preservation of saved hours/senders. |
| Sequence templates | Two built-in templates visible: Connect and follow up; Profile warm-up. Preview shows the stored branches, delays and sample message. | Existing gallery, custom templates, compiler, typed conditions, preview and revision governance remain. Unsupported actions/conditions remain unavailable. |
| Sender setup | Credentials with country/premium-product selection; session-cookie form with optional premium cookie and user agent. Forms were inspected without submitting LinkedIn credentials. | Encrypted asynchronous cookie verification remains the supported path. Fixed disconnect/install races and reconnect state. Credential/2FA automation and a browser extension are not implemented by this release. |
| Launch | Prerequisites exposed by UI; no trial, sender, leads or physical launch verified. | Preflight and authoritative launch both reject missing/invalid prospect progress, removed senders, unassigned progressed conversations and terminal-only campaigns. Execution still requires separate content, permission, inbox, proxy, paid-term and restore checks. |

Prosp's [import guide](https://help.prosp.ai/en/articles/9268317-how-to-find-and-import-leads), [campaign guide](https://help.prosp.ai/en/articles/10348281-create-a-campaign), [builder guide](https://help.prosp.ai/en/articles/10348371-using-the-builder-all-actions-and-conditions) and [credential-connection guide](https://help.prosp.ai/en/articles/10348233-connect-a-linkedin-profile-using-credentials) were also read. The older import guide includes event/group sources that were absent from this session's five-choice dialog. The guides describe product contracts; they do not substitute for a successful live test.

## Implemented repairs

### Lead generation and intake

- Direct CSV confirmation now carries the same optional strict required-name policy used for preview. Legacy API callers retain the prior default when they omit the option.
- Raw CSV confirmation retains invalid source rows in its accounting. Editing a preview no longer loses the row's location or silently resurrects a deliberately cleared name.
- Missing-name rows can be corrected and explicitly revalidated. Changed direct CSV/profile rows cannot be committed using stale preview counts. The new permission-guarded `POST /leads/preview-staged` rechecks server policy and provenance; commit still validates independently.
- Direct preview always evaluates DNC and email exclusions. A new exclusion between preview and confirmation still blocks admission.
- Empty, partial or contradictory nested identifiers cannot bypass same-batch deduplication. Canonical current email/member/Sales Navigator/vanity identities are retained in existing top-level fields while normalized saved aliases stay in `identifiers`; later imports and preview round-trips match both.
- Staged search edits retain their original job-bound commit path, including explicit empty-name overrides. Its mandatory contacted exclusion cannot be toggled away. The direct-import revalidation workflow does not deadlock this separate path.
- Late preview, file-reader and commit results cannot update a closed or changed importer context. Existing unknown-outcome/batched-search holds remain. The source-collection gate remains disabled.

Existing historical rows whose identities were previously lost or stored unnormalized were not backfilled. This repair prevents future loss; it does not claim complete historical identity reconstruction. Supplied aliases remain caller-provided identity evidence, not independently authenticated ownership.

Generic importer fencing covers the current open/campaign/generation context. Broader authentication-token/workspace-switch invalidation remains a separate gap; these repairs do not claim complete browser-context isolation.

### Sequence and launch

- Auto-draft accepts only draft/paused records and valid authorization/claim state. It matches the original native record, status, authorization revision, admission revision and launch claim before writing; a competing activation/save returns conflict. Each successful settings save advances authorization revision.
- Outstanding leads assigned to removed/invalid senders hold. Missing senders are accepted only for scalar queued, unacted root records awaiting their first assignment. Wait states, earlier actions, nonroot progress and malformed array-shaped authority cannot silently receive a different sender.
- Removed/invalid current steps and missing steps with prior action/wait evidence hold. No automatic re-rooting, sender migration or conversation restart is introduced.
- Campaigns containing only finished/replied/bounced/failed/staged records cannot become active with no outstanding work. Valid existing root delays remain intact.
- Reopening numeric-weekday schedules preserves custom start/end times and timezone. Loading senders cannot silently replace a stored unavailable sender with the first active account; the UI retains it and explains the required review.
- Voice recording/upload buttons and unused fallback input are visibly unavailable. Profile dwell-time and repeat-visit controls are disabled and explained as unapplied by the current runner. Existing saved values are retained; no unverified transport behavior is invented.

Same-ID semantic replacement of an in-progress node still needs a reviewed migration policy. The new guard catches missing/invalid references; it does not certify every historical step's meaning.

### Senders

- Disconnect atomically removes usable session credentials, closes installation fences, records the disconnect boundary, stops/scrubs pending custody, pauses/disarms affected campaigns and cancels queued tasks using either sender-reference field. Existing provider leases, paid-term slots, locks and uncertain work evidence are retained for their established cleanup/repair owners.
- An earlier captured verification cannot reactivate an explicitly disconnected account. A genuinely later explicit reconnect can proceed through current authority checks.
- Verified reconnect clears session-expiry and proven elapsed recoverable stops. Future/malformed cooldowns, security challenges and unknown stop reasons remain held.
- The connection modal accepts saved running/finalizing/repairing/terminal job acknowledgements and reads the original job before reporting an account. Read failure/timeout exposes **Check verification status**, which checks the same job rather than submitting credentials again. Closed/context-changed responses do not announce success.
- Sender accounts expose an explicit Refresh control and reject malformed successful list responses. Stale list reads cannot undo a confirmed local disconnect projection.

Job references remain modal-local: closing/reloading loses that reference. The new retry and refresh controls are not durable cross-reload job discovery.

## Verification

- Broad backend, excluding `tests/sandbox`: **4,424 passed, 2,505 skipped, six warnings in 279.62 seconds**. The selected 206 native checks below are opt-in skips in this run, so **4,630 distinct backend checks passed across the two selections**, with no passing overlap. Remaining optional/historical skips were not rerun as a full native suite.
- The first broad run retained four failures (4,416 passed, 2,505 skipped). Older template tests lacked current UID/member/erasure observations or assumed every reader used the ordinary authentication dependency. Test-only fixtures now exercise the real access service; the two existing snapshot-owning readers retain their exact authentication/delegation contract. Four additional HTTP regressions verify unauthenticated denial and current-context delegation. The focused 305 checks and final broad rerun pass; production template API/access sources remain byte-identical to HEAD. Initial failures remain in the evidence directory.
- Whole frontend: **696 tests, 61 suites passed**. Independent final source review reran **73 tests across eight affected suites**; these overlap the whole run.
- Compiled synthetic browser flows: **14 passed**, including two new working-hours/sender-continuity and original-job-recovery journeys. APIs/external requests are intercepted; these are not live LinkedIn/provider tests.
- Selected native backend: **206 distinct passing checks** across lead intake/admission/list imports (77), readiness (122), and sender disconnect/install (7). They use owned disposable loopback databases, including standalone denial. These module selections are not a fresh full native application suite.
- Independent backend source/test review: **43 pure and 33 selected native checks passed**; these overlap the larger runs. Both earlier high-severity review findings were corrected with failing regressions before passing reruns.
- Production frontend build passes with existing dependency/source-map/Tailwind warnings. Scoped Python compilation, medium/high Bandit and diff checks pass. Supported CRA lint reports no errors and existing unused-code/style warnings.
- Default pytest plugin autoload cannot start because the installed pytest-celery plugin requires missing `pkg_resources`. Verification explicitly disables autoload and loads pytest-asyncio; no dependencies or global settings were changed. Optional/historical native drills and sandbox API tests are not certified by a non-native run.

Evidence is under `/tmp/unravler-flow-audit-RX116d`: red/green logs, independent reviews and source hashes, browser/build logs, REA input manifests and retained views. Root `.coverage` remains byte-identical to its preexisting SHA-256 `4b74da9b0ce92d241eb136c8d09b5716e661366ef11ff2f8a1bf666257de94ba`. Existing user MongoDB/Redis services and unrelated worktrees/files are preserved. A final preservation manifest records intended overlaps; no full-application coverage percentage or live fidelity claim is made.

## Remaining implementation plan

| Priority | Work | Required edge cases and completion evidence |
| --- | --- | --- |
| P1 | Atomic sender identity claims and existing duplicate review | Two simultaneous jobs for one LinkedIn member; reconnect versus new sender; aliases/changed identity; workspace policy; erasure/release; standalone and unknown commit outcomes. Existing non-atomic worker precheck is not sufficient. Do not add a naive production unique index over unreconciled data. |
| P1 | Durable sender job discovery and status UI | Close/reload, token/workspace changes, two pending jobs, lost POST acknowledgement, stopped/repaired/failed/completed states and changed account identity. Persist only scoped references; no cookies or credentials in browser storage. |
| P1 | A real lead-source adapter and truthful capability activation | Select a supported data-provider contract before activating Basic/Sales Navigator/post/network/finder collection. Fixture-verify pagination, schema changes, limits, resumable checkpoints, cancellations, no-results/partial results, per-source provenance, duplicates/DNC and current authorization. Add native admission/concurrency tests and a controlled authorized integration pilot. No fabricated leads or parser-only success. |
| P1 | Reviewed migration for existing sender/sequence progress | Missing original sender, same-ID step replacement, outstanding invite/reply waits, physical unknown outcomes, version changes and preserved delays. Explicit review must precede any re-root/reassignment. |
| P2 | Complete lead management UX | Source/location/column filters and custom-field mapping, per-row validation/rejection export, list/campaign assignment, large files, duplicates within/across pages, stale review, auth/workspace switches and exclusion changes. Existing list import recovery remains the stronger recoverable path. |
| P2 | Real sequence capability expansion | Comment/reply/InMail/follow/endorsement/read/open-profile features only after recipient/evidence/transport contracts and end-to-end runner checks exist. Voice record/upload/fallback requires a real artifact preparation/approval path. Keep unsupported controls unavailable until then. |
| P2 | Sender usability and accurate readiness | Credential/2FA or extension onboarding needs its own authentication/session-custody design. Show actual stop/cooldown/resource/effective-limit information; current raw status, static warmup level and configured-proxy badge do not prove execution readiness. |
| Operational | Controlled release and pilot | Keep current live and snapshot flags off. Resolve existing R2/password-reset readiness conditions; verify storage/key/IAM/network/provider access, paid term/proxy/inbox evidence and real pilot separately. Review and commit/deploy this local repair before calling it production behavior. |

Read-only template history viewer, separately reviewed restore and the prior snapshot cutover/index/key-custody backlog remain open and are independent of this repair.
