# Unravler.io — Voice vendor evidence and hold release

Date: 2026-10-05. Twenty-first bounded local slice, architecture v2.22.0.

## Result and scope

A trusted private operator can now capture a single bounded ElevenLabs voice-metadata GET, retain its minimal evidence durably, and separately release an existing profile review hold through an exact database-only transaction. Both operations require disabled live/Studio/campaign-preparation flags and an explicit all-workspace-writer/cache drain. Release stops current workspace sender/campaign authority, increments the profile revision and preserves consent and unrelated physical tokens. It never resumes a campaign or grants an outreach action.

The profile must already have its current scoped provider source and an original clone receipt, directly or through the twentieth-slice proven same-key lineage. This supplies vendor evidence/review-hold release only for such proven instant-clone profiles. Different-key migration, missing/unproven legacy profiles, professional/mixed/non-owned voices and broad vendor account adoption remain outside scope. A human assertion, API visibility or possession of a new key cannot replace original proof.

## Vendor evidence and local acceptance policy

The documented [Get voice endpoint](https://elevenlabs.io/docs/api-reference/voices/get) supplies the remote voice ID, category, resource permission, ownership and voice-verification fields. This implementation uses that fixed metadata endpoint, with no library search, sample fetch, TTS, clone/delete or verification/captcha mutation. The raw response may contain private sample and verification content; only a bounded allowlist of facts is retained.

Local release policy is deliberately narrow: exact remote identity; `category=cloned`; explicit `is_owner=true`; resource permission exactly `admin`; explicit non-legacy/non-mixed booleans; `safety_control=NONE`; explicit `requires_verification=false`; and a boolean `is_verified`. If the original clone required verification, current `is_verified=true` is mandatory. A clone whose original receipt explicitly did not require verification may have `is_verified=false` only when current metadata explicitly says verification is not required. Missing, null, malformed, unexpected permission/category or challenge/ban facts keep the hold. These are local policy restrictions, not a claim that all owner responses contain `admin` or that metadata grants outreach/platform permission.

Vendor facts describe the keyed read at that time. They do not certify speaker identity beyond the returned verification field, permanent vendor permission, present/future account billing, operational drain, or LinkedIn authorization. Local recorded consent is independently mandatory and unchanged. There is no ongoing vendor status monitor in this slice.

## Durable one-operation metadata read

`outreach/core/voice_vendor_evidence.py` records a permanent `outreach_voice_vendor_reads` job before key opening. The exact inspection binds complete profile/original clone/source lineage/configuration plus bounded Studio/preparation/account/campaign/execution/permission rows and prior profile reads. Each family caps at 100; creation reserves space for its new permanent read. Pending Studio or metadata work, live sender leases, active claimed/generating preparation work, closed tenants, malformed identities, unavailable scoped source, changed snapshots and capacity gaps deny.

The first snapshot/majority workspace transaction uses the shared suppression guard and write-fences inspected rows. It creates a request-idempotent `preparing` record with original owner, operator/evidence digests, original clone/profile/configuration/source digests and a 60-second permission deadline. Prepared key opening happens outside retryable Mongo callbacks. A second snapshot/majority transaction revalidates exact authority and current key configuration, then atomically charges the independent 20-GET workspace/day budget and marks the read `possible`. HTTP runs only after that commit and a synchronous deadline/configuration/flag check.

The production adapter makes exactly one `GET https://api.elevenlabs.io/v1/voices/{bounded-id}`. It disables redirects/environment proxy inheritance and automatic retries, requests identity encoding, accepts only 200 JSON with identity encoding, and caps the streamed body at 256 KiB. Its SDK/client boundary repeats permission/key checks. The complete provider operation has a 30-second outer timeout and a 25-second HTTP timeout. No response URL is followed. Read allowances are local budgets; this does not imply that vendor reads are free.

The receipt stores only the nine metadata facts, schema version and original received timestamp, bound by a normalized UTC digest. It never retains names, descriptions, samples, voice verification recordings, arbitrary response properties, raw key or envelope. Exact original owner/status CAS saves the receipt. A changed configuration during GET retains the original response evidence while preventing release. A response received after the one-operation deadline also cannot authorize release. An acknowledgement lost after receipt commit reuses the saved receipt without opening custody or repeating HTTP.

Identical capture retries return the existing record in its current state. They never resume `preparing`/`possible` or call the provider again. A proven pre-call failure can become `stopped` without charging a budget; once the possible marker commits, its budget remains charged even if no packet or response can be proven. No automatic retry/publisher is added for this private one-operation workflow.

## Interrupted read closure

Private `close-read` requires disabled flags, exact complete inspection, identified drain and expiration of the original permission. Only an exact original preparing/possible job without a receipt can close. It becomes `stopped` if no possible marker exists, otherwise `read_interrupted`; original owner/possible/budget/source proof remains. Closure is explicitly a read-interruption decision, not a mutation outcome or vendor verification. Identical retries reuse its permanent operator/evidence/inspection hashes; conflicting review inputs deny.

After closure a separately inspected new read can be authorized and charges its own allowance. The original job is never replayed. Closed erasure tenants cannot capture/release/close through this normal open-workspace protocol; their existing drained erasure procedure retains minimal unresolved read evidence.

## Database-only hold release

A selected saved receipt must be from the exact current profile revision/consent/status/review hold, current scoped source/full configuration and original clone/root remote identity. Receipt timestamps must be ordered within the original physical permission, not in the future and younger than 15 minutes at release. Vendor acceptance facts, all-writer drain, complete current authorities and disabled flags are checked under the shared snapshot/majority guard. All matching read authorities are write-fenced.

The transaction pauses current sender/campaign authority, disables auto-launch, increments campaign authorization revisions, latches permissions without clearing unrelated physical tokens/owners and cancels queued campaign voice preparations. Only then can the exact original profile become `active`, clear `studio_review_required` and increment its revision. The selected read records an embedded permanent `saved_vendor_metadata` release journal and evidence/profile/inspection/operator digests. Original consent, assignments, Studio jobs and clone receipts remain intact. Revoked/malformed consent, changed remote/profile/source/configuration, uncertain original mutations, malformed/expired/denied vendor evidence or new work preserve the hold.

Freshness, current configuration and flags are checked again after awaited stop work and at the final journal boundary. Journal failure, expired evidence or configuration change rolls back profile release and authority changes together. Identical concurrent/lost-ack release retries return the saved journal without HTTP, key opening or repeated stops. Historical retry reports `current_matches=false` after profile/configuration replacement and never writes the replacement. No vendor call, audio open/generation, campaign resume, payment or execution grant occurs during release. The new profile revision invalidates old campaign clip/content-approval identities; new preparation/review is still required before future use.

Checks are process-local and transaction-bound; this is not global revocation of an already authorized call. Actual fleet drain/config propagation, workload IAM and kernel/process egress isolation remain operational requirements. Older/raw writers outside the guard are not brought into the protocol by this slice.

## Shared transaction commit recovery

The first broad regression run exposed an existing concurrent first-collection commit conflict: the installed Motor 3.4.0 transaction context surfaced a `TransientTransactionError` before its explicit commit retry path. The isolated old case passed, but that did not close the retry gap. Seven deterministic driver-fault tests first reproduced the missing retry and distinguish aborted, unknown and unlabeled commits. [Motor's transaction contract](https://motor.readthedocs.io/en/3.4.0/api-asyncio/asyncio_motor_client_session.html) permits a database callback to execute more than once and distinguishes transient aborts from uncertain commit results.

The shared suppression helper now permits at most two extra database-only restarts for an explicitly labeled transient abort. Each restart uses a fresh session after the previous session closes, under the unchanged single 10-second timeout and snapshot/majority concerns. Unknown-commit labels take precedence even when a transient label is also present; unknown/unlabeled failures and cancellation do not trigger an outer callback replay. Existing driver-level retry behavior is retained. HTTP/key work stays outside those callbacks. This change applies to the shared suppression helper; it does not replace every other legacy transaction helper or globally resolve uncertain commits.

## Indexes, erasure and private operation

Startup removes evidence TTLs from Studio jobs, source journals and vendor read records before strict builds. The new collection has unique workspace/profile/inspection identity and a partial unique active read per profile. Index errors are not ignored. An actual standalone MongoDB server denies before key opening/HTTP, with no production transaction fallback.

Erasure classifies the new collection, purges private reads/journals and retains minimal hashes, source/root/config/profile/receipt/inspection identifiers, read outcome/time, operator/evidence hashes and optional release provenance. It excludes raw remote identity, vendor metadata/body, narratives, audio, key/envelope and activation/replay grants. Existing remote-profile cleanup retention remains separate; this read/release does not imply remote deletion or whole-product erasure. Drain older erasure writers before rollout.

The CLI is private and reference-only; there is no customer endpoint. Use the trusted operations host with existing Mongo configuration and reviewed scoped key configuration. All flags stay off. Drain every API/media/beat/Studio/profile/consent/campaign/integration/transport/mailbox/connection/suppression/erasure writer and cached authority. Resolve pending Studio/campaign work first. Operator identity and drain are private-host assertions, not automatic authentication or process detection.

```bash
python -m outreach.ops.voice_vendor_review inspect \
  --workspace <workspace-id> --voice <local-profile-id>

python -m outreach.ops.voice_vendor_review capture \
  --workspace <workspace-id> --voice <local-profile-id> \
  --operator <operator-id> --evidence "Private audit reference and complete writer/cache drain evidence" \
  --review-digest <exact-inspection-digest> \
  --workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES

python -m outreach.ops.voice_vendor_review inspect \
  --workspace <workspace-id> --voice <local-profile-id> --job <saved-read-id>

python -m outreach.ops.voice_vendor_review release \
  --workspace <workspace-id> --voice <local-profile-id> --job <saved-read-id> \
  --operator <operator-id> --evidence "Private audit reference and complete writer/cache drain evidence" \
  --review-digest <fresh-inspection-digest> \
  --workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES
```

`capture` explicitly performs a provider GET and custody open; it must be separately authorized for a real environment. `inspect`, `release` and `close-read` perform database/metadata work only. For expired interrupted work, use `close-read` with the selected read reference and a fresh inspection digest. No secret is accepted as a CLI argument; parser/runtime output is static on failures and successful JSON contains only allowlisted local references/status/availability/digest. Do not include secrets or sensitive narratives in public shell arguments. No production command/configuration/key was installed or invoked in this slice.

## Remaining work

This closes bounded current-source instant-clone vendor evidence/review release. Different-key and unproven legacy adoption still need a distinct evidence protocol rather than relaxing original-root/source checks. Other shared/provider/Webshare secrets, older campaign artifacts, actual IAM/process/kernel egress and restore fencing, broader retention/integration boundaries and separately authorized IPRoyal/mailbox/voice pilot evidence remain. Verified-invoice provisioning stays manual; automatic billing/proxy procurement remains deferred.

## Verification and delivery

All 103 new checks pass in the current focused run: 77 service/private CLI/adapter cases, 15 actual Mongo checks (14 replica-set plus one standalone denial), four fresh-process SIGKILL cases and seven deterministic driver commit-retry cases. All four process drills use the production metadata state machine/GET adapter over real loopback TCP, with a test custody stand-in; no external egress, AWS or live vendor request. Key opening is separately tested with local custody fakes outside Mongo callbacks. Combined statement coverage across the three new modules is 98% (service97/adapter100/CLI98). The affected suppression run passes all 40 checks (seven driver faults plus 33 existing real ordering cases).

Independent Python review approved the bounded code/report after the release freshness/configuration gap and shared-voices wording were corrected. The reviewer reran 77 vendor units and seven driver-fault cases plus an independent cancellation check, without starting services concurrently. Compile, medium/high Bandit, both Compose configurations and whitespace checks pass. Compose validation with the existing backend environment reports the existing unset-key warnings. Frontend code is unchanged; prior 93 frontend tests/build remain historical evidence.

The initial broad run had 1,658 passing checks, 44 historical opt-in skips and one concurrent first-collection transient commit failure. That failure led to the bounded shared-helper fix and deterministic red/green tests; it was not dismissed as a passing isolated rerun. The complete clean rerun after the fix passes **1,666 backend checks (1,646 outreach plus 20 account/auth companions)**, with **44 historical opt-in drills skipped**. Earlier loopback suites also reran; no new Redis/Celery redelivery or real vendor/AWS/IAM/egress/restore proof is implied. Existing python_multipart/fork deprecations remain.

Cleanup and delivery: owned temporary databases were removed/confirmed absent, replica/standalone Mongo storage is removed, and ports 27028/27029/6389 are closed. No Redis was started. All three repo/Desktop v2.22 specifications and 86 relative links/21 unique supporting reports byte-match. Pre-edit backup: `/tmp/unravler-docs-before-v2-22`. Prior dirty files, unrelated worktrees and services are preserved. Local only: no commit, push, deployment, real AWS/vendor call, purchase or production grant; default legacy custody and disabled live/generation/Studio flags remain.
