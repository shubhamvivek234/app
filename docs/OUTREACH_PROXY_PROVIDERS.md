# Paid outreach pilot: sender seats and dedicated IPs

## Passive verified-evidence health window (local v2.34)

This private controller renews only an existing explicit unlatched LinkedIn permission with matching original connection/install/read proof. It does not issue the initial grant, open keys, probe LinkedIn/proxies, clear stops or launch/resume campaigns. Its gate defaults false; live outreach remains separately disabled. Deployment/configuration and an actual operator arm require separate operational authorization. Configure and drain a uniform fleet when changing custody/environment policy; this command installs no configuration.

On the trusted backend host, inspect with `python -m outreach.ops.health_monitor inspect --workspace WORKSPACE --sender SENDER`. Preserve the metadata-only digest and independently review every blocker and original verification/permission. Arm only a valid current inspection with `python -m outreach.ops.health_monitor arm --workspace WORKSPACE --sender SENDER --operator OPERATOR --evidence-digest REVIEW_EVIDENCE_SHA256 --review-digest INSPECTION_DIGEST --window-seconds 300`. Window range is 1–900 seconds; original health proof lasts at most 90 seconds regardless of window. Arming grants nothing; the 30-second worker issues at most 60-second permissions capped by all captured deadlines. No further observation is fabricated.

Stop an exact control with `python -m outreach.ops.health_monitor stop --workspace WORKSPACE --control CONTROL_SHA256 --operator OPERATOR --evidence-digest REVIEW_EVIDENCE_SHA256`. Existing/newer permission decisions remain independently authoritative; obsolete controllers preserve replacements. A current stop latches permission and pauses the bounded selected campaign scan without clearing physical tokens, unknown outcomes or budgets. Returned `campaign_pause_scan_complete=false` requires separate campaign inspection. Revoking the monitor flag denies subsequent control-derived dispatch entry. Work already physically submitted retains its normal evidence/reconciliation path.

Keep original journals and remove unsafe control TTLs before strict startup index builds. A duplicate armed sender fails startup and needs private review rather than deletion of evidence. Closed tenants never renew. The control is finite passive monitoring; active health probes, cohort/challenge thresholds and restore fencing remain follow-ups. Full scope: [v2.34 health control release](UNRAVLER_IO_HEALTH_MONITOR_RELEASE.md).

## Related maintenance: unsubmitted Studio input stop (local v2.33)

Recognized queued or expired-preparing clone/preview jobs can be privately stopped and their encrypted inputs scrubbed without opening audio/text/keys. Original native job/protocol/profile ownership is mandatory. Possible/received/held work, unknown fields, missing original proof, live/unproven owners or changed profiles stay outside this path. Only an exact unused clone placeholder is removed; preview consent/status/vendor resource/assignments remain, with revision advanced and a review latch blocking new use. No input rewrap, replay, refund, vendor deletion confirmation or activation is supplied.

Keep live outreach, integrations, Voice Studio and voice preparation disabled and pause/drain every workspace writer/cache. Independently preserve original job/profile evidence. Inspect: `python -m outreach.ops.voice_studio_input_cutover inspect --workspace WORKSPACE --job ORIGINAL_JOB_SHA256`. Review blockers and the exact digest. Apply: `python -m outreach.ops.voice_studio_input_cutover stop --workspace WORKSPACE --job ORIGINAL_JOB_SHA256 --operator OPERATOR --evidence-digest REVIEW_EVIDENCE_SHA256 --review-digest INSPECTION_DIGEST --workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES`. References/digests contain no secrets; there are no sample/script/password/replay/activation inputs.

Snapshot/majority stop, profile cleanup/latch, job scrub and metadata receipt commit together. Failures roll back together. Tokens/budgets/uncertainty remain; recognized queued sibling inputs are stopped separately. Exact saved retries repeat no stop/cleanup; a current mismatch preserves replacements. Input prefix recognition is metadata only, without authenticating ciphertext. Drain is operator asserted and raw/older writers remain outside participating protocol proof. Unsupported standalone Mongo denies without fallback. Retention-first strict indexing and minimal erasure provenance preserve local stop evidence; closed tenants cannot recreate purged work. Complete scope and local verification: [v2.33 input cutover release](UNRAVLER_IO_STUDIO_INPUT_CUTOVER_RELEASE.md).

## Related maintenance: completed Studio preview results (local v2.32)

Eligible original results must be completed/unexpired previews with strict Fernet, a valid original received audio receipt, native dates, expired original owner lease and matching local voice/resource/source with no active Studio slot. The encrypted original tenant/job/payload/result context and actual WAV/audio digest are verified before KMS work. Pending input, held/unknown outcomes, unproven/expired previews and older synchronous samples are not converted.

Keep live outreach, integrations, Voice Studio and voice preparation disabled; configure scoped destination and pause/drain all workspace writers/caches. Independently retain/review original job/profile/receipt evidence. Inspect on the trusted backend host: `python -m outreach.ops.voice_studio_migration inspect --workspace WORKSPACE --job ORIGINAL_JOB_SHA256`. Review blockers and preserve its exact digest. Apply only an eligible result with `python -m outreach.ops.voice_studio_migration migrate --workspace WORKSPACE --job ORIGINAL_JOB_SHA256 --operator OPERATOR --evidence-digest REVIEW_EVIDENCE_SHA256 --review-digest INSPECTION_DIGEST --workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES`. References/digests contain no secrets; no audio/password/script/source/generation/expiry inputs exist.

Preflight commits sender/campaign/permission stops before opening/wrapping and cancels known queued campaign preparation. Profile consent/revocation and unknown paid/physical evidence remain. Final ciphertext/journal installation is atomic; failed key/install leaves original preview and stopped authority, requiring fresh inspection absent a receipt. Exact saved retries open nothing and repeat no stop. Retain original external evidence and metadata receipts; drain remains an operator assertion.

Original audio, receipt, job configuration and exact expiry stay unchanged; no synthesis/provider request replays or lifetime extensions occur. The original job configuration can still fail normal current playback checks after a custody change; separately authorized new preview preparation may be needed. This command supplies no playback/activation/configuration grant and is not deployed. Complete scope and verified local evidence: [v2.32 Studio result release](UNRAVLER_IO_STUDIO_PREVIEW_CUSTODY_MIGRATION_RELEASE.md).

## Related maintenance: installed campaign recording custody (local v2.31)

Only an unexpired original campaign WAV with strict Fernet, native original dates, a received preparation-job result and a full retained review reconstructing the original workspace/content/generation/audio identity is eligible. This private workflow changes storage ciphertext while preserving bytes, generation, media facts and original expiry; it performs no synthesis or source adoption. Missing/expired/unproven recordings and older Studio caches remain blocked.

Keep live outreach, integrations, Voice Studio and voice preparation disabled; configure the scoped destination and pause/drain all workspace writers and caches. Independently retain and review the original evidence. On the trusted backend host, inspect `python -m outreach.ops.voice_artifact_migration inspect --workspace WORKSPACE --artifact ORIGINAL_ARTIFACT_SHA256`, review every blocker and preserve the exact digest. Apply with `python -m outreach.ops.voice_artifact_migration migrate --workspace WORKSPACE --artifact ORIGINAL_ARTIFACT_SHA256 --operator OPERATOR --evidence-digest REVIEW_EVIDENCE_SHA256 --review-digest INSPECTION_DIGEST --workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES`. References/digests must contain no secrets; there are no audio/password/source/generation/expiry inputs.

Preflight commits paused workspace sender/campaign authority and approval invalidation before opening audio/key work. Rejected/revoked decisions and unknown paid/physical holds remain. Final ciphertext and permanent metadata journal install atomically. If opening/wrapping/install fails without a receipt, preserve the stopped original source and inspect again. Exact saved retries open nothing and grant no activation; preserve original receipts/evidence. Drain is operator asserted and actual fleet/config cutover requires separate proof.

Original recording expiry continues. Current profile/source/recipient/campaign/consent and content review still gate use; pausing can stale the original campaign binding. Fresh review alone cannot rebind that clip, so changed context may require new normal preparation under separate authorization. No command is deployed or enables flags. Full scope and verified evidence: [v2.31 recording migration release](UNRAVLER_IO_INSTALLED_VOICE_ARTIFACT_MIGRATION_RELEASE.md).

## Retained-evidence legacy Webshare adoption (local v2.30)

Older Webshare inventory can enter managed scoped custody only when its original record already retains complete original owner/purchase/term/transport evidence. The command opens and rewraps the existing strict-Fernet password; it preserves existing proxy generation or allocates only a missing one, and preserves lease/cookie generation/stopped permission. Bare helper records missing original facts remain blocked. No replacement password, original purchase facts, provider request, payment grant or activation is supplied. This section supersedes earlier adoption targets only for this bounded retained-evidence case.

1. Independently verify retained original workspace/sticky owner, dedicated ISP plan/resource/order/operator/evidence, native database verification/expiry dates and exact transport. Missing, expired, conflicting or unknown facts require a separate protocol; do not manufacture fields to satisfy this command. Keep external original evidence separately.
2. Disable live outreach, integrations, Voice Studio and voice preparation; configure scoped destination custody and drain all participating workspace writers/caches. Inspect using `python -m outreach.ops.proxy_adoption inspect --workspace WORKSPACE --asset webshare:PLAN:RESOURCE` and retain the exact digest. Resolve blockers separately.
3. Apply with `python -m outreach.ops.proxy_adoption adopt --workspace WORKSPACE --asset webshare:PLAN:RESOURCE --operator OPERATOR --evidence-digest REVIEW_EVIDENCE_SHA256 --review-digest INSPECTION_DIGEST --workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES`. No password/URL/cookie/order/expiry argument exists. References/digests must contain no secrets.
4. Retain the metadata receipt and original evidence. Permanent physical exclusion precedes key work: a failed seal/install or lost preflight acknowledgement can retain exclusion without capacity. If no adoption receipt exists, preserve records and reinspect; never remove the claim or enable flags to bypass a stale digest. Exact saved retries perform no opening/sealing/reinstallation and report historical completion plus current/configuration matches; they never resume work.

Capacity, reconnect, storage conversion and later reviewed term/password changes require permanent adoption lineage. Partial/stripped/mismatched history denies while journals remain. Tenant erasure retains minimal hashed provenance and permanent physical exclusion; closed tenants cannot reinstall after purge. Drain remains operator asserted, and actual provider/IAM/kernel-egress/restore/pilot evidence remains separate. No command in this section is deployed or grants activation. Full scope and local evidence: [v2.30 adoption release](UNRAVLER_IO_LEGACY_WEBSHARE_ADOPTION_RELEASE.md).


## Reviewed Webshare term and password recording (local v2.29)

For a proven v2.27 managed Webshare asset, the private operator workflow can record an already externally completed renewal or password change. It preserves original ownership/purchase evidence, IP/transport, lease/reservation, cookie generation and paused permission. Renewal changes the provider expiry; password recording updates inventory and matching sender copies atomically with a new proxy generation. This local workflow performs no Webshare request, purchase, renewal, vendor password change, payment grant or activation. Its evidence is operator asserted, not a vendor receipt.

1. Disable live outreach, integrations, Voice Studio and voice preparation. Independently verify and record the completed provider change and original asset evidence, then drain all participating workspace writers and caches. Keep a nonsecret provider reference plus a SHA-256 evidence digest.
2. Inspect using `python -m outreach.ops.proxy_lifecycle inspect-renew --workspace WORKSPACE --asset webshare:PLAN:RESOURCE` or `inspect-rotate`. Review blockers and preserve the exact returned `digest`; do not bypass mismatched ownership, claim, lease, history, aliases or stopped authority.
3. Run `renew` or `rotate` with those references plus `--operator OPERATOR --evidence-digest EVIDENCE_SHA256 --provider-reference CHANGE_REFERENCE --review-digest INSPECTION_DIGEST --workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES`. Renewal also requires `--expires-at` with an explicit timezone, strictly extended future expiry at most 366 days ahead. Rotation reads the already changed password through a hidden prompt; optional `--stdin` supplies bounded input. Passwords/URLs/cookies have no command arguments.
4. Preserve the metadata receipt and original external evidence. An exact saved retry needs no input/key work and can report historical completion after term expiry; inspect current matching/configuration fields separately. A receipt never resumes work. Reusing its provider reference for different review/target denies. Closed tenants cannot recreate authority after purge.

Capacity/reconnect/storage conversion now require the permanent original-root/current-revision journal for reviewed assets. Missing or removed lineage markers do not supply original proof. Strict index conflicts need separate drained repair. Older/unproven Webshare adoption, different IP/resource/owner and IPRoyal term/password lifecycle remain unsupported by this command. Actual provider validity, fleet drain, IAM, kernel egress, backups/restore and authorized pilot behavior remain separate evidence. Full procedure and local verification: [v2.29 lifecycle release](UNRAVLER_IO_PROXY_TERM_AND_ROTATION_RELEASE.md).

## Reviewed proxy custody conversion (local v2.28)

For an already imported v2.27 managed Webshare asset, strict-Fernet to scoped conversion is available without changing its original generation, term, import proof, physical claim, lease/reservation or paused sender. Older helper records cannot enter this path without original ownership/purchase/assignment evidence. Existing stopped IPRoyal conversion remains compatible. This is not deployed and does not grant sender/campaign activation.

1. Disable live outreach, integrations, Voice Studio and voice-preparation gates. Drain all participating workspace API/worker/credential writers and caches. This is an operator assertion requiring real fleet verification at cutover.
2. Configure the scoped destination policy; run `python -m outreach.ops.proxy_custody inspect --workspace WORKSPACE --asset webshare:PLAN:RESOURCE`. Resolve blockers separately and preserve the exact returned `digest` plus original evidence.
3. Run `python -m outreach.ops.proxy_custody migrate --workspace WORKSPACE --asset webshare:PLAN:RESOURCE --operator OPERATOR --evidence-digest ORIGINAL_REVIEW_SHA256 --review-digest INSPECTION_DIGEST --workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES`. Digests are 64 lowercase hex; do not put credentials in metadata arguments.
4. Exact receipt retries report historical completion plus current material/configuration matches without opening/resealing or reinstalling. A false match means current records/configuration differ; it does not reverse the old completion or permit adoption. Unknown commit acknowledgement is resolved through that receipt. If no receipt exists, reinspect before retry; do not enable flags to bypass a blocker.

The new CLI accepts no proxy URL/password/cookie arguments and sanitizes errors. Original import-basis evidence must remain independently available. Real IAM/provider validity, kernel/process egress, fleet drain, backups/restore and approved pilot use remain separate verification. Full protocol and local evidence: [v2.28 migration release](UNRAVLER_IO_MANAGED_PROXY_MIGRATION_RELEASE.md).


## Managed Webshare imports (local v2.27)

Paid sender reservations now accept new, manually verified Webshare dedicated static ISP inventory as well as IPRoyal. This local change is not deployed. The Webshare API selection helper does not establish paid inventory ownership or a provider term. Older/unproven Webshare rows require separate drained review and remain blocked; Reviewed scoped custody conversion of proven managed assets is locally implemented in v2.28 below; reviewed term/password recording is available locally in v2.29 above; unproven adoption remains separate.

After independently verifying the dedicated, nonrotating ISP plan, exact resource, country, original order and expiry, retain the source evidence separately and compute its SHA-256 digest. Run on the trusted backend host with the configured database and encryption environment:

```bash
python -m outreach.ops.webshare_inventory \
  --workspace WORKSPACE_ID --plan PLAN_ID --resource PROXY_RESOURCE_ID \
  --order VERIFIED_ORDER_ID --country IN --expires-at 2026-12-01T00:00:00Z \
  --operator OPERATOR_ID --evidence-digest ORIGINAL_EVIDENCE_SHA256 \
  --confirm-dedicated-static-isp
```

The authenticated HTTP proxy URL is read through a hidden prompt. Explicit `--stdin` accepts bounded input; keep secrets out of command arguments/history, chat and logs. No vendor API, purchase, renewal, payment grant or live flag is invoked. The digest-only physical-IP assignment is permanent and survives tenant erasure; mistaken/failed imports can retain an exclusion claim without capacity. Inspect before retrying. An exact committed retry returns `already_imported` and keeps the original encrypted password/generation even if a different password was supplied. It never rotates credentials or extends the provider term. See the [implementation and limits](UNRAVLER_IO_MANAGED_WEBSHARE_PROVISIONING_RELEASE.md).

This is an **invite-only, manually fulfilled pilot**, not a self-service
subscription. The displayed price is $59 USD per sender per month (1–5 seats).
The app does not charge a card, issue invoices, purchase proxies, or renew
provider orders. Never grant access based only on a customer's request or a
claimed payment; an operator must verify the invoice independently.

Session-based LinkedIn outreach uses unofficial APIs and may violate LinkedIn's
terms or lead to account restrictions. A residential/ISP IP, rate limits, or
human-like delays do **not** make it authorized. Keep
`OUTREACH_LIVE_ACTIONS_ENABLED=false` until product/legal approval and a live
technical smoke test. Do not enable `OUTREACH_MOCK_AUTH` for a paid sender.

## Customer and operator flow

1. The workspace owner submits a paid-access request with sender-seat count
   and intended two-letter proxy country. This records demand only.
2. An operator confirms availability, acceptable use, the sender's usual
   country, price and the prospective paid-through date. The current pilot
   supports **one requested country per workspace**; mixed-country teams need
   manual review and a future per-seat country schema.
3. After the operator verifies the provider order, import **one unique,
   dedicated static ISP IP per sender** into the workspace-bound inventory.
   Do not use a rotating residential, shared datacenter or SOCKS-only proxy.
   Each provider term must cover the entire customer paid period.
4. After independently verifying the external invoice is paid, record the
   invoice ID and entitlement with the private CLI. The invoice ID is unique
   and cannot be reused for a different workspace or terms. If the receipt is
   written but entitlement update fails, reconcile the two records manually;
   do not invent a second invoice ID.
5. Once live actions are explicitly enabled, the owner selects that country
   and supplies `li_at` and `JSESSIONID`. The API queues encrypted values;
   the worker checks the leased IP and verifies the LinkedIn identity. The
   connection is shown as ready only after the worker confirms it. Secrets
   are scrubbed from the pending job after completion or failure.

Run the private CLI on the trusted backend host with `DB_NAME`, `MONGODB_URI`
and `ENCRYPTION_KEY` set. Keep proxy credentials out of shell history, command
arguments, Git, chat, and frontend variables. The import reads
`IPROYAL_PROXY_URL` from the operator process environment; clear it after use.
Example commands (replace IDs and dates with verified values):

```bash
python -m outreach.ops.pilot list-requests
python -m outreach.ops.pilot import-iproyal --workspace WORKSPACE_ID --country IN --order-id VERIFIED_PROVIDER_ORDER --expires-at 2026-11-30T00:00:00Z
python -m outreach.ops.pilot record-payment --workspace WORKSPACE_ID --invoice-id VERIFIED_PAID_INVOICE --operator OPERATOR_ID --seats 1 --paid-through 2026-10-27T00:00:00Z --verified-in-processor I_VERIFIED_THIS_INVOICE
python -m outreach.ops.pilot list-expiring --days 7
```

Use the HTTP port and URL-encoded credentials for the purchased public static
IP. Import pre-binds it to one workspace; an atomic lease assigns it to at
most one sender. Failed verification can release a *new* reservation, but a
connected sender keeps its lease on disconnect, cancellation and lapse.
Never auto-recycle a previously used IP to another customer.

## Renewal, cancellation, lapse and return

The owner can request cancellation at the end of the paid period. This does
**not** stop an IPRoyal/Webshare order; the operator must separately disable
provider auto-renewal and record the provider's actual expiry. Preserve the
sender's paid IP assignment until that expiry; do not discard paid time.

At customer paid-through, the periodic worker expires entitlement, pauses
campaigns, cancels queued outreach, invalidates stored sender sessions and
pending connection values. Action workers also recheck paid access and the
provider term before making calls. No grace access or automatic reactivation
is granted. If the same customer pays again while the IP is still valid,
verify the new invoice, extend the provider order if needed, then record the
new term and reconnect the sender. If the provider term has expired, import
a newly purchased IP for the same workspace and reconnect; the old lease is
kept in history. Changing IP may carry account risk, so do not promise that
it is harmless.

If country-specific capacity is unavailable, keep the request pending and
tell the customer before taking payment; never silently substitute country
or a shared/free proxy. A new customer does not receive another customer's
held IP even when that customer's subscription has lapsed. Restriction or
checkpoint events pause the sender and require investigation; do not silently
rotate the IP and retry.

## Legacy provider path and readiness limits

The earlier Webshare plan-backed connection code remains in the repository,
but this paid pilot's managed inventory currently imports IPRoyal static IPs
only. Switching the old `OUTREACH_PROXY_PROVIDER` environment variable does
**not** migrate managed leases or enable self-service Webshare procurement.
That migration requires separate inventory import, lease transfer, and live
validation before launch.

Tests use mocks and cannot establish that a purchased IP, LinkedIn session,
provider acceptable-use policy, billing workflow, and the external worker all
work together. Do not call the pilot production-ready without those checks.

## Local operator repair protocol

The local v2.6 implementation adds drained job review, account installation fences, pending custody deadlines, and job-owned reservation cleanup. Follow the [operator repair and custody runbook](UNRAVLER_IO_OPERATOR_REPAIR_AND_CUSTODY_RELEASE.md) for sanitized inspection and repair commands. Keep live flags disabled and drain old workers before any separately approved rollout. Human confirmation does not become provider evidence; ambiguous legacy or installed assets remain bound.

## Local erasure and provider-term retention protocol

The v2.10 implementation stops each actually owned outreach tenant and scrubs secrets before purge. Even empty tenants require all-writer drain; obtain sanitized inspection/current digest and use the private finish-erasure CLI only after that drain. Retained inventory/leases remain tenant-bound, with no credentials or recipient content. Retention release requires the current owned asset and its verified ended term; missing ownership, renewal or unknown expiry denies release. Deleted workspaces reject fresh proxy import/payment/execution grants. No provider purchase, cancellation or remote erasure is performed by these commands. Follow the [erasure and retention runbook](UNRAVLER_IO_ERASURE_AND_RETENTION_RELEASE.md) for private commands, pending account retries and the remaining cache/backup/remote-copy/SDK limits. Keep live actions disabled pending separately authorized operational verification.

## Local managed password custody and storage-orphan closure

The v2.13 implementation extends opt-in KMS custody to managed IPRoyal passwords. Workspace/asset/generation/transport context is separate from the sender lease. Keep live services drained while migrating both inventory and proven sender copies; KMS mode rejects unscoped passwords and Webshare provisioning remains separate. The private storage-stop command releases only job-owned unused reservations after exact protocol/base-account/no-install evidence review and saves a permanent closure first. Reconnect/ambiguous connected resources stay held. Follow the [proxy custody and storage repair runbook](UNRAVLER_IO_PROXY_CUSTODY_AND_STORAGE_REPAIR_RELEASE.md); keep flags disabled pending actual IAM, kernel egress, restore and purchased-seat/mailbox verification.

## Local mailbox and finder custody conversion

The v2.14 implementation adds installed mailbox/OAuth/Hunter contexts and conservative durable refresh holds. The private provider migration requires all credential writers and caches drained, all workspace senders stopped, no held provider work and an exact bounded inspection. It preserves mailbox identity/cursors and stopped permissions; receipt retries perform no key or provider calls. See the [mailbox and finder custody procedure](UNRAVLER_IO_MAILBOX_AND_FINDER_CUSTODY_RELEASE.md). Keep flags disabled: shared OAuth app secrets, Voice Studio/Webshare custody, full durable OAuth/sync lifecycles, actual IAM, kernel egress, restore and purchased-seat/mailbox evidence are still separate.

## Local durable OAuth connection cutover

The v2.15 implementation keeps broker failures queued, permanently holds ambiguous OAuth exchanges, and atomically records mailbox installation receipts. Before first cutover, drain old/new OAuth, paid/erasure, transport, publisher/recovery and credential writers/caches; verify transactions and retention-first indexes. Do not delete or reset a review row to reconnect. New and reconnect mailboxes still wait for healthy/fresh reply synchronization before email. This slice does not yet supply a drained OAuth hold-resolution command or the complete durable sync HTTP lifecycle. Follow the [durable mailbox connection release](UNRAVLER_IO_DURABLE_MAILBOX_CONNECTION_RELEASE.md); keep flags disabled pending remaining custody/IAM/routing/restore and purchased-seat evidence.


## Local OAuth review and durable mailbox sync cutover
The fifteenth slice adds a private drained stop-only OAuth hold command, durable sync selection/publication, conservative bounded physical GET receipts and exact cursor/projection recovery. Review requires disabled live actions, an exact sanitized inspection digest and the all-mailbox-and-sender-writer drain acknowledgement; it stops local authority without claiming provider revocation. Completed cached bodies are scrubbed atomically; failed/stopped caches have bounded cleanup, while receipt metadata remains. Do not delete/reset held OAuth rows to reconnect. Drain all older/new participating writers and verify strict mailbox/job/read/budget indexes and transactions before rollout. Full procedure: [OAuth review and durable sync](UNRAVLER_IO_OAUTH_REVIEW_AND_DURABLE_SYNC_RELEASE.md). This work is local only; actual workload IAM, kernel egress, restore fencing, app/shared-secret custody and operational pilot checks remain separate.

The v2.17 local application OAuth custody slice adds encrypted-only Gmail/Microsoft app secrets, job configuration proof and stable mailbox/app identity checks for refresh and reconnect. Configuration rotation requires drained process replacement; older KMS rows with missing app proof need renewed offline authorization. The private sealer does not deploy or rotate provider grants. Follow the [application OAuth custody runbook](UNRAVLER_IO_OAUTH_APP_CUSTODY_RELEASE.md); keep existing flags disabled.


## Stopped restore admission (v2.35, local only)

Keep the restored environment isolated with every writer/cache drained and all five settings exactly `false`: `OUTREACH_LIVE_ACTIONS_ENABLED`, `OUTREACH_INTEGRATIONS_ENABLED`, `OUTREACH_VOICE_STUDIO_ENABLED`, `OUTREACH_VOICE_PREPARATION_ENABLED`, `OUTREACH_HEALTH_MONITOR_ENABLED`. Rotate a unique 64-character lowercase hex `OUTREACH_EXECUTION_EPOCH` in the external deployment configuration; do not restore/reuse it from a database or configuration backup. Explicitly set `OUTREACH_RESTORE_FENCING_ENABLED=true` consistently across the drained fleet. These instructions configure nothing automatically; no production cutover was performed.

Run private `python -m outreach.ops.restore_epoch inspect --workspace WORKSPACE`, then review its metadata counts, blockers and exact digest. Use `prepare --workspace WORKSPACE --operator OPERATOR --evidence-digest DIGEST --review-digest EXACT_INSPECTION_DIGEST --all-writers-and-caches-drained` only after the identified drain and outside-backup identity review. The CLI accepts no cookies, keys, provider URLs, activation or replay options and never returns credential/content material. Evidence is a digest of independently retained operator evidence; the drain flag is an assertion, not a process census. More than 100 rows in any inspected collection or a malformed original root requires a later bounded cutover, not a bypass.

`prepared=true` means the root and stops were committed. `activation_allowed=false` remains mandatory. Keep all provider work stopped while reconciling lost reply/DNC/deletion/financial/remote-resource evidence. Exact retries recover the saved journal without repeating stops; an old anchor never replaces a newer root. Credentials, uncertain/received evidence, physical tokens, budgets and leases are deliberately retained. No epoch grant, automatic queued-job retagging or restored activation is implemented. Independent inventory/provisioning/billing/cleanup tools and key-service operations still need their own drained operating controls and restore proof. Removing the epoch/flag cannot reopen an installed root; retaining an anchor denies even if an older backup erased the root. Older runtimes or restoration of both external identity and database are outside this protection.

See [restore-epoch release](UNRAVLER_IO_RESTORE_EPOCH_RELEASE.md) for coverage and limits. Next: outside-backup deletion/suppression/financial reconciliation, a controlled isolated restore/IAM/egress drill and explicit new-epoch activation design. No production flags or grants should be enabled on this evidence alone.


## Selected restore deletion exclusions (v2.36, local only)

A trusted operator can export one already-closed workspace guard and 1–100 explicitly selected retained global identity digest tombstones to an exclusive 0600 file in an owned private directory: `python -m outreach.ops.restore_exclusions export --workspace WORKSPACE --identity-digest DIGEST --output-file PRIVATE_FILE`. These are selected negative facts, not an ownership mapping or complete inventory. Keep the artifact and its independently verified provenance outside backups; the byte digest establishes integrity, not source authenticity. No original production data was exported during implementation.

On an isolated target whose deletion guard was lost, first prepare the matching stopped v2.35 epoch with all five execution/health flags false and every writer/cache drained. Never bypass an existing closure to create a missing epoch: an already-closed target without matching admission remains outside this importer. Inspect with `python -m outreach.ops.restore_exclusions inspect --workspace WORKSPACE --manifest-file PRIVATE_FILE` (or bounded `--manifest-stdin`). Review counts/source/review digests, then use `apply` with the same source plus `--operator`, `--source-digest`, `--evidence-digest`, `--review-digest` and `--all-writers-and-caches-drained`. Keep the original digests for receipt recovery.

Successful import reinstates selected UID digest denies and a `restore_excluded` workspace hold, with a permanent metadata journal. It preserves existing exclusions, timestamps, request records, credentials/resources and physical uncertainty. It does not purge, claim erased/completed, reopen jobs or authorize activation. More than 100 selected identities, unsafe files, changed source/review/configuration or missing current exclusions on receipt retry deny. See the [selected-exclusion release](UNRAVLER_IO_RESTORE_EXCLUSIONS_RELEASE.md). Suppression/reply/financial/provider completeness, explicit activation and actual isolated restore/IAM/egress proof remain separate.

## Selected recipient suppression restore (v2.37, local only)

Use the private [selected DNC/email restore procedure](UNRAVLER_IO_RESTORE_SUPPRESSIONS_RELEASE.md) for explicitly retained original recipient blocks lost by older backups. Source export and target apply require all-writer/cache drain assertions; inspect/apply require the matching stopped epoch and all five flags off. Closed tenants cannot export/import recipient data or use saved receipts to recreate it. The private artifact contains recipient identifiers and original times; establish its provenance and keep it outside backups. Selected blocks restore neither reply history nor completeness, and never grant activation. Build the strict retention-first indexes on a drained fleet; duplicate workspace/email data denies cutover. Broader reply/financial/provider reconciliation and actual restore/IAM/egress drills remain separate.


## Selected sender-specific LinkedIn reply-stop restore (v2.38, local only)

Use the private [selected reply-stop procedure](UNRAVLER_IO_RESTORE_REPLY_STOPS_RELEASE.md) for retained original LinkedIn thread replies lost by older backups. Export selects thread `_id` references, supported recipient URN/optional profile URL and stored native reply time, with at most 100 expanded facts/64KiB. Source app sender ID/current stored LinkedIn mapping must exactly match the existing target; old threads do not prove the historical external sender, and legacy remapping can conservatively over-block. No automatic sender adoption/remap is supplied. Private files and source provenance/storage outside backups are operator responsibilities; majority reads/drain assertions do not prove atomic or complete recovery.

With writers/caches drained, all five flags off and the matching stopped v2.35 epoch prepared, inspect exact counts/digests and apply the same reviewed source. Closed tenants and changed/missing sender mappings deny; saved receipts require all current negatives. The separate negative collection reaches LinkedIn sequence reply preflight, retaining sender scope and bare/www URL matching. It does not create messages/reply metrics/freshness/branch evidence or grant activation, and it supplies no new manual Engage/reply/email policy. Retention-first strict indexes deny duplicate cutover rows; erasure purges private negatives and keeps hashed provenance. Keep execution stopped; remaining financial/provider evidence/completeness, activation design and restore/IAM/egress drills remain separate.

## Selected invoice reuse exclusions (v2.39, local only)

On a trusted drained source, select 1–100 original global invoice-guard `_id` digests and export with `python -m outreach.ops.restore_invoices export --workspace WORKSPACE --invoice-digest DIGEST --output-file PRIVATE_FILE --all-writers-and-caches-drained`, repeating `--invoice-digest`. Use an owned private directory. Imported/blocked guards are not original export sources. The hashes do not prove payment or invoice ownership: a retained guard may be an interrupted reservation. Workspace selects review scope only. Establish provenance independently and retain private artifacts outside backups; export is individual majority reads, not an atomic/complete/authenticated inventory.

On an isolated target, keep all five flags false, drain writers/caches and prepare the matching stopped v2.35 epoch. Run `python -m outreach.ops.restore_invoices inspect --workspace WORKSPACE --manifest-file PRIVATE_FILE` (or bounded `--manifest-stdin`). Review exact bytes/digests/counts, then use `apply` with the same source, `--operator`, `--source-digest`, `--evidence-digest`, `--review-digest` and `--all-writers-and-caches-drained`. Missing root, changed binding/review or malformed/missing saved block denies; permanent reuse blocks never grant access. Hash-only import preserves closed targets only when a matching root already exists; it cannot bypass closure/preparation after full erasure. Retain original review digests for retries and keep execution stopped afterward.

Payment finalization now orders request/entitlement/receipt/global invoice authority with epoch/erasure; a stopped restored epoch or recovered block denies new payment access. Successful exact receipt retries preserve current inactive/revoked state and the private pilot output reports that state. Existing request/future-term/capacity preflight remains; capacity is not transactionally reconciled here. No payment, entitlement, owner, provider resource, grant or activation is reconstructed. A later exclusion does not revoke already committed access. Review the [v2.39 scope, tests and remaining limits](UNRAVLER_IO_RESTORE_INVOICE_EXCLUSIONS_RELEASE.md) before any operational use. This procedure has not been run on production.

## Selected physical-IP restore exclusions (v2.40, local only)

Deterministic IPv4 hashes remain linkable and candidate addresses can be enumerated/matched; manifests remain private artifacts.

Independently identify selected original global `account_proxy_ip_guards._id` digests and trusted provenance. They attest local reservation/assignment, possibly interrupted; they do not prove vendor ownership/payment/term. Workspace binds review scope only. After draining source writers/caches, export 1–100 hashes with `python -m outreach.ops.restore_proxy_exclusions export --workspace WORKSPACE --ip-digest DIGEST --output-file PRIVATE_FILE --all-writers-and-caches-drained` (repeat the digest option). Keep the exclusive0600 artifact and independently verified origin outside backups. Individual majority reads/asserted drain are not complete, atomic or authenticated inventory; the app cannot verify storage location.

On the isolated target, prepare the matching stopped v2.35 epoch with all five flags false and all writers/caches drained. Inspect via `python -m outreach.ops.restore_proxy_exclusions inspect --workspace WORKSPACE --manifest-file PRIVATE_FILE` (or bounded `--manifest-stdin`). Apply the same source using `apply`, exact `--operator`, `--source-digest`, `--evidence-digest`, `--review-digest`, and `--all-writers-and-caches-drained`. Retain original hashes for retries. Imported facts are permanent reuse blocks only: no raw IP, vendor fact, inventory, credential, lease, grant or activation is recovered. Global fence rows order participating checks/imports even when an original guard is missing, but do not supply ownership. Conflicting first fence upserts can deny safely; inspect/review rather than bypass.

Restored blocks now stop participating managed imports/reservations, readiness/physical dispatch, connection verification/installation and custody/lifecycle work. Actual embedded and present inventory hosts both count. Closed-target hash-only import requires an existing matching stopped root and never clears closure; full erasure removes that root/journal. Minimal hashes and permanent global negatives/fences remain. Preserve credentials, leases, tokens, budgets and uncertain evidence. Local admission does not cancel already-admitted calls, prove complete provider/financial recovery or enforce older/raw/fleet/kernel behavior. Follow the [physical-IP restore exclusion release](UNRAVLER_IO_RESTORE_PROXY_EXCLUSIONS_RELEASE.md) and keep execution stopped pending remaining evidence and explicit activation design. This local implementation performs no production export/import or provider/AWS operation.

## Isolated physical backup/restore rehearsal (v2.41, local only)

The combined drill uses an independently owned disposable `unravler-test` replica on fixed `127.0.0.1:27028`, synthetic UUID source/target databases, and real mongodump/mongorestore. Both `OUTREACH_TEST_LOCAL_MONGO=1` and `OUTREACH_TEST_PHYSICAL_BACKUP=1` are required for `tests/test_outreach_restore_backup_drill.py`; missing tools fail an explicitly requested drill. Test flags/epochs are scoped to the process, not real deployment configuration. Generated targets are replaced before each restore because --drop alone retains collections absent from the archive. Never substitute production data or a user database.

The two cases each restore twice, lose/reimport all five selected exclusion sources, preserve held/financial/resource evidence and keep permissions stopped. Private manifests are outside this database archive only; source authenticity/completeness, production/Atlas/oplog recovery, fleet/cache/IAM/kernel egress and activation are not established. Review the [physical backup/rollback rehearsal](UNRAVLER_IO_RESTORE_BACKUP_REHEARSAL_RELEASE.md) for exact scope, invocation, final results and cleanup. Application code, production settings and providers remain unchanged; selected negatives never grant activation.


## Forty-first slice: stopped financial and proxy reconciliation inventory (v2.42)

Private selected local metadata inspection requires matching prepared stopped epoch, five flags off and asserted all-writer/cache drain. A single guard/snapshot/majority session covers seven selected collections and global invoice/IP binding lookups; existing guard/root/journal fence metadata may advance while domain resources, credentials, receipts, tokens, budgets and unresolved evidence remain intact. Capacity is 100 rows per collection/65,536 serialized metadata bytes checked after reads, not a wire-memory bound. Candidate legacy proxy and lease presence does not establish ownership. Missing, malformed, blocked and expired evidence is reported; even empty or matching results never certify completeness, provider ownership or activation. Private digests bind only selected snapshot metadata and remain linkable. No apply/grant/activation, provider call, new journal/index or frontend change. Same-session concurrent-write, native BSON bindings and actual standalone denial checks pass; 33 focused cases,98% coverage and independent Python review. 512 restore regression checks pass (103.26s, one existing warning), with two opt-in physical-backup drills skipped. Two subsequently added native checks also pass in the final33-case focused run: 514 distinct passing checks across these runs. No fresh full-backend or physical-backup result is claimed. Procedure, evidence and limitations: [forty-first-slice release](UNRAVLER_IO_RESTORE_RECONCILIATION_INVENTORY_RELEASE.md).


## Forty-second slice: stopped financial consistency and physical evidence review (v2.43)

The private inventory compares entitlement invoice identity, integer seats, native UTC-millisecond paid term and manual payment source with the selected original receipt; missing/mismatched/unproven,stopped/revoked and expired terms are reported. Physical requests explicitly report preparing, unresolved, response-received and unrecognized states without resolving/replaying/refunding or altering evidence. payment_source enters the projected digest, so prior digests may change. Existing v2.42 stopped-epoch/five-flags/drain assertion/same-session/seven-collection100-row/after-read64KiB bounds apply; existing fence metadata may advance, while domain records remain intact. No authenticated payment, source completeness, provider ownership or activation is established, even with matching local guards.57focused pass(44unit/CLI+13native),24new cases,98%coverage. Final restore regression:538 passed,2 opt-in physical-backup drills skipped,one existing warning in100.36s; no fresh full-backend or physical-drill claim. Approved after correcting inconsistent failed-read metadata; independent44 unit/CLI checks pass. Procedure and limits: [forty-second-slice release](UNRAVLER_IO_RESTORE_FINANCIAL_CONSISTENCY_RELEASE.md). Local only; no commit/push/deploy/provider/AWS/purchase/grant/flag changes; frontend unchanged.


## Forty-third slice: stopped proxy assignment consistency review (v2.44)

Private inventory adds selected lease/asset/application-sender relation findings: malformed identities, multiple leases, missing/ambiguous sender, current/sticky scope contradiction, provider/country mismatch, changed proxy ID or credential generation. Pending reservations without installed accounts require review; local matches never prove ownership, credentials, provider lineage, capacity or activation. New country/provider/proxy-generation projections bind the snapshot digest; secret-only changes remain excluded. Existing stopped-epoch/fiveflags/drain-assertion/same-session/seven-collection100row/after-read64KiB contract applies. Guard/readfence counters may advance; domain evidence/resources/leases/reservations remain intact. 78 focused checks pass(58 unit/CLI+20 native Mongo)in17.17s;21 new cases(14unit+7native). Coverage99%combined(core99%,CLI97%). Final independent Python review approves;58 independent unit/CLI cases pass and scoped Bandit is clean. Final restore suite:559 passed,2 opt-in physical-backup drills skipped,one existing warning in106.55s. Native duplicate accounts are explicitly index-free legacy evidence. No new schema/index/journal/apply/grant/activation/provider call or frontend change. Procedure/evidence/limits: [forty-third-slice release](UNRAVLER_IO_RESTORE_PROXY_ASSIGNMENT_REVIEW_RELEASE.md). Local only; no commit/push/deploy/real credential/AWS/provider/purchase/grant/flag change.


## Forty-fourth slice: stopped Webshare lifecycle metadata review (v2.45)

Private inventory adds current Webshare lifecycle marker/receipt consistency: workspace/sticky scope,strict bounded integer revision,hex basis/review markers,receipt ID/completed status/current material and credential-generation digests. Missing/changed/ambiguous evidence requires review; original imports without lifecycle receipts are conservatively unproven here, not operationally invalidated. Older revisions do not create current-revision ambiguity. This does not certify adoption/import/provider ownership/credentials/capacity or activation. An eighth projected collection,outreach_proxy_lifecycle_reviews,shares the100rows-per-collection/whole64KiB after-read budget,same stopped-epoch/fiveflags/drainassertion/snapshot contract; source projections/digests expand. No domain mutation/schema/index/journal/grant/activation/provider action. 92 focused checks pass(67 unit/CLI+25 native Mongo)in18.31s,14 new cases(9unit+5native);99%combined coverage(core99%,CLI97%). Independent Python review approves;67 independent unit/CLI cases pass and scoped Bandit is clean. Final restore suite:573 passed,2 opt-in physical-backup drills skipped,one existing warning in109.98s. Evidence and limits: [forty-fourth-slice release](UNRAVLER_IO_RESTORE_WEBSHARE_LINEAGE_REVIEW_RELEASE.md). Local only; no commit/push/deploy/real credential/AWS/provider/purchase/grant/flag changes; frontend unchanged.


## Forty-fifth slice: stopped Webshare adoption metadata review (v2.46)

Private inventory compares retained Webshare adoption markers with exact resource/ID/completed/source/basis receipts under current/sticky workspace scope. Missing/malformed/foreign/changed/ambiguous facts require review; absent-root fallback is allowed,present-null root cannot fall back. Original imports without adoption evidence are conservatively reviewed,not operationally invalidated. Matching retained metadata never authenticates source/journal/adoption,proves ownership/completeness or authorizes use; adoption/lifecycle findings remain independent. Ninth projected collection outreach_proxy_adoptions shares100rows each/whole64KiB after-read bounds,same stopped-epoch/fiveflags/drainassertion/snapshot contract. No domain mutation/schema/index/journal/grant/activation/provider action. 108 focused checks pass(78 unit/CLI+30 native Mongo)in24.11s,16 new cases(11unit+5native);99%combined coverage(core99%,CLI97%). Independent Python review approves;78 independent unit/CLI cases pass and scoped Bandit is clean. Its two recommended null-root/receipt-ID regressions were added and pass in the final focused run. Restore suite:587 passed,2 opt-in physical-backup drills skipped,one existing warning in125.81s. Two later added unit cases also pass in the final108-case focused run:589 distinct passing checks across these runs. Procedure and limits: [forty-fifth-slice release](UNRAVLER_IO_RESTORE_WEBSHARE_ADOPTION_REVIEW_RELEASE.md). Local only; no commit/push/deploy/real credential/AWS/provider/purchase/grant/flag change;frontend unchanged.


## Forty-sixth slice: stopped Webshare import metadata review (v2.47)

Private inventory checks selected provider IDs/canonical asset ID,current-sticky-custody scope,strict managed version/dedicated marker,bounded review/generation references,hex evidence/import-basis metadata and native nonfuture verification/future paid-term ordering. Missing/malformed/contradictory facts require review. Consistent metadata is not webshare_basis_valid: credential-bearing fields are excluded,the original full basis is not recomputed,no original/provider/payment fact or provenance is authenticated,ownership/completeness/use authorization remain false. Independent import/adoption/lifecycle/lease/binding findings never authorize activation. Nine collections retain100rows each/whole64KiB after-read budget,same stopped-epoch/fiveflags/drainassertion/snapshot contract; projection/digest scope expands. No domain mutation/schema/index/journal/grant/activation/provider action. 126 focused checks pass(91 unit/CLI+35 native Mongo)in23.10s,18 new cases(13unit+5native);99%combined coverage(core99%,CLI97%). Final independent Python review approves;91 independent unit/CLI checks pass. Its colon-in-plan/resource-ID finding was fixed with two regressions; no remaining material finding. Final restore suite:607 passed,2 opt-in physical-backup drills skipped,one existing warning in125.19s. Procedure/evidence/limits: [forty-sixth-slice release](UNRAVLER_IO_RESTORE_WEBSHARE_IMPORT_METADATA_RELEASE.md). Local only; no commit/push/deploy/real credential/AWS/provider/purchase/grant/flag change;frontend unchanged.


## Forty-seventh slice: stopped sender-to-proxy assignment review (v2.48)

Private inventory checks reverse application-sender→asset→lease links: malformed/duplicate sender identities,shared proxy references,missing/foreign-sticky assets,missing/ambiguous/wrong-sender/multiple leases,provider/country/generation disagreement. Missing reverse relationships now explicitly require review. Local matches never establish authentication/credentials/health/paid term/import/adoption/lifecycle/binding/ownership/completeness or use permission; all finding groups remain independent. Existing projections/ninecollections100each/whole64KiB afterreads and stopped-epoch/fiveflags/drainassertion/snapshot contract remain; no domain mutation/new field/schema/index/journal/grant/activation/provider action. 150 focused checks pass(107 unit/CLI+43 native Mongo)in31.77s,24 new cases(16unit+8native);99%combined coverage(core99%,CLI97%). Independent Python review approves;107 independent unit/CLI cases pass,eight native contracts inspected without service actions. Final restore suite:631 passed,2 opt-in physical-backup drills skipped,one existing warning in129.03s. Legacy duplicate/shared-account native fixtures are index-free; matching Webshare labels do not certify import validity. Procedure/evidence/limits: [forty-seventh-slice release](UNRAVLER_IO_RESTORE_SENDER_ASSIGNMENT_REVIEW_RELEASE.md). Local only;no commit/push/deploy/real credential/AWS/provider/purchase/grant/flag change;frontend unchanged.


## Forty-eighth slice: stopped email and finder operation review (v2.49)

Private inventory adds _id/status projections for outreach_email_operations and outreach_email_discoveries: dispatching/uncertain unresolved,kind-specific terminal recorded-result review,missing/malformed/unrecognized/wrong-kind states unproven. Quiet not_submitted metadata never proves a non-call,replay/refund/reclaim permission. Recorded states are not authenticated provider outcomes/delivery/billing. Eleven collections retain100rows each/whole64KiB afterreads,same stopped-epoch/fiveflags/drainassertion/snapshot contract; tokens/recipients/receipts/history/results excluded,domain evidence untouched. No repair/resolution/replay/refund/newschema/index/journal/grant/activation/provider call. Other OAuth/mailbox/voice/integration families remain outside this addition. 174 focused checks pass(125 unit/CLI+49 native Mongo)in39.46s,24 new cases(18unit+6native);99%combined coverage(core99%,CLI97%). Independent Python review approves;125 independent unit/CLI cases pass,six native contracts inspected without service actions. Final restore suite:655 passed,2 opt-in physical-backup drills skipped,one existing warning in133.20s. Procedure/evidence/limits: [forty-eighth-slice release](UNRAVLER_IO_RESTORE_PROVIDER_OPERATION_REVIEW_RELEASE.md). Local only;no commit/push/deploy/real credential/AWS/provider/purchase/grant/flag change;frontend unchanged.


## Forty-ninth slice: consolidated stopped uncertainty inventory (v2.50)

The private inventory adds nine intact-row metadata projections for OAuth connection/browser states, mailbox refresh/sync jobs/reads, campaign voice preparation, Studio jobs, voice vendor reads and webhook/HubSpot deliveries. Pending/preparing/unresolved/recorded-result/stopped labels all require review; malformed or unknown required states are unproven. Separate exchange/refresh/original Studio outcome/generation-result findings survive stopped parent states. Missing refresh is unmarked review, not proof of no call. No status authenticates receipt/non-call/revocation/refund/replay permission. Twenty collections retain 100 rows each and a whole-view 64KiB after-read bound, the existing stopped-epoch/five-flags/drain-assertion/snapshot contract, and private aggregate output. Domain evidence/budgets are preserved; no repair/resolution/replay/new schema/index/journal/grant/activation/provider action. This selected intact-row inventory excludes erasure archives, missing provider facts and added LinkedIn-finalization/manual/sequence-intent census; completeness/ownership/activation remain false. Focused verification: 265 checks pass (196 unit/CLI and 69 actual Mongo checks) in 41.57s. The 91 added checks comprise 71 unit and 20 native cases. The initial 71 new unit cases failed before implementation. Combined statement coverage is 99% (inventory 99%, uncertainty classifier 100%, CLI 97%). Independent Python review approves with no remaining material findings: 196 independently executed unit/CLI checks pass, and the 20 new native contracts were inspected without service actions. Compile, scoped Bandit and whitespace checks pass. Final restore regression: 746 passed, two opt-in physical-backup drills skipped, and one existing multipart deprecation warning in 131.42s. Procedure, exact scope and limits: [forty-ninth-slice release](UNRAVLER_IO_RESTORE_UNCERTAINTY_INVENTORY_RELEASE.md). Next: authenticated outside-backup reconciliation/completeness and unproven reply evidence, then explicit activation design/drills. Local only; no commit/push/deploy/real credential/AWS/provider/purchase/grant/flag change; frontend unchanged.
