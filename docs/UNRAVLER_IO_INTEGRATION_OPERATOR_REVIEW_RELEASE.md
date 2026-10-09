# Integration operator review and credential migration — v2.24

Updated: 2026-10-08. Status: locally implemented and verified; uncommitted and not deployed.

## Outcome and bounded scope

Private operator tools now inspect and resolve held webhook, Slack and HubSpot deliveries, and convert an existing strict-Fernet integration credential into scoped KMS storage. Delivery review never opens a key or makes an HTTP request. Migration opens the original encrypted value and seals the same value outside Mongo transactions; it does not contact the integration vendor. Neither operation activates a connection or campaign.

The tools require all four integration, LinkedIn live-action, Voice Studio and campaign voice-preparation flags disabled, a bounded operator identity and evidence note, the exact inspection digest, and an explicit assertion that all workspace writers and caches are stopped and drained. This assertion is not a discovered fleet-drain proof. Inspection captures the original job, current source and custody policy, persistent resource control, sender/campaign/permission authority and applicable CRM lead/mapping identity. Each captured collection is capped at 100 rows; excess capacity, malformed sender identity and other live or unproven integration writer leases deny repair. Existing matching authority rows are write-fenced under the shared workspace guard in snapshot/majority transactions. A standalone Mongo database cannot perform the operation; no fallback bypasses transactions.

## Original delivery evidence and local stop

| Original evidence | Allowed local result |
|---|---|
| Protocol-v2 preparation with attempt zero, no possible marker and no receipt, after a proven lease expiry | Cancel the original job and release only its original active slot |
| Missing, malformed, interrupted or unproven submission outcome | Save a local-stop journal; keep the original job in review and retain its CRM slot |
| Intact saved original 2xx receipt, exact owner/timing/source/policy and applicable CRM lead/mapping identity | Apply that receipt to local records without sending again; preserve original received time |
| Saved non-success receipt, including an ambiguous HubSpot 409 | Permit local stop only; a recorded HTTP response is not proof that the remote mutation did nothing |
| Legacy leased or quarantined snapshot delivery | Stop and scrub locally; no replay, source adoption or invented non-call proof |

Only the current original authorized attempt can supply a usable receipt. Immutable job identity, receipt digest, possible/received/authorization timing and the original owner must match. A worker-projected receipt whose lease was cleared must have exactly one matching saved attempt-owner proof. A receipt from an earlier webhook retry cannot prove the outcome of a newer preparation or possible attempt. A successful CRM receipt additionally requires a bounded numeric contact ID and the captured original lead/mapping basis. Current remote observations cannot replace these original facts.

Before applying any local repair, the transaction pauses existing senders and active/warming campaigns, advances campaign authorization revisions and stops existing execution permissions. It preserves unrelated physical submission tokens, owners, leases and attempt/budget history. Known pending/retry work for the same destination is cancelled. Exact successful-receipt projection uses `review_completed` and frees only the original slot; uncertain stop uses `review_required` and keeps the slot. Local-stop provenance stays distinct from a saved provider receipt and from verified engagement or remote account ownership.

An independent permanent resource-control latch blocks delivery and settings resave. It survives ordinary disconnect/reconnect even when local configuration is deleted. The source row also remains paused and review-required when present. A completed review or migration does not remove either hold. A future explicit activation protocol is separate work; an ordinary settings save cannot reactivate a held resource.

Historical webhook jobs that omitted `destination_type`, or stored it as null, are included in review and credential-migration backlog checks. If their source was deleted, a bounded original saved URL and encrypted signing-secret reference can prove only which local record to stop and scrub. Original plaintext URL, encrypted URL, signing secret and copied access token fields are removed from that job; no field is opened, copied into new configuration or adopted as current authority. Saved review journals remain inspectable after this scrub or source deletion.

One permanent journal binds the original workspace/job, inspection digest, decision, operator/evidence hashes, original outcome and observed timing. The receipt projection, authority stop, exact cleanup and journal commit together. Journal-write failure rolls everything back. A lost completion acknowledgement can retry the identical reviewed decision and return its saved journal without another stop, mapping update, key opening or HTTP request; changed review arguments deny. Late flag or custody-policy changes abort the transaction.

## Credential storage conversion

Migration accepts only a proven existing strict-Fernet webhook secret, Slack URL or HubSpot token while the configured destination mode is scoped `kms_v1`. Plaintext, already-scoped values, cross-workspace bindings, missing source identity, closed tenants and held/unproven original delivery outcomes deny. Known pending/retry jobs can be cancelled under the stop transaction; an unknown CRM slot or legacy leased backlog cannot be silently cleared to permit migration.

Two guarded transactions surround key work outside Mongo: first inspect/fence the exact original authority, then revalidate, stop authority and conditionally install the converted ciphertext with a permanent metadata-only receipt. Existing credential generation is preserved; a missing generation is allocated once for the committed conversion. The target envelope binds the original resource, workspace, purpose, environment and generation. Original ciphertext/source replacement, policy changes or flags enabled between these boundaries prevent installation. A saved completion retry skips all key work and reports whether the current resource and configuration still match; it never adopts a replacement or stops authority twice.

This is same-value storage conversion, not a provider-account ownership proof, credential rotation, different-key adoption or activation. Actual KMS access uses the existing custody implementation and requires separately verified workload IAM/configuration at rollout. The local tests use stand-ins and make no real AWS request.

## Private entrypoint, retention and cutover

`outreach.ops.integration_review` exposes `inspect-delivery`, `resolve-delivery`, `inspect-credential` and `migrate-credential`. Arguments are bounded workspace/delivery/resource references and review metadata. Mutation requires the exact drain acknowledgement `I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES`. There are no URL, raw credential, HTTP or activation arguments. Parser/runtime failures are sanitized, including accidental credential-like arguments. The customer delivery UI recognizes completed operator projection and explains that the connection remains paused.

Review/resource-control/migration evidence has no TTL. Global startup and the integration index cutover remove evidence TTLs before later strict index creation; duplicate evidence aborts cutover rather than being ignored. Strict indexes preserve one original review and one inspected migration identity. Erasure keeps minimal hashed review, unresolved-submission, resource-stop and migration provenance without payloads, destination URLs, keys, ciphertext or remote contact IDs. Closed-tenant local stop creates no new source/permission/resource authority. Broader backups, vendor copies and legal retention remain outside this slice.

Before using these tools in production:

1. Keep all four flags disabled and stop/drain the complete API, worker, beat, integration, transport, inbox, mailbox, consent/profile, connection and erasure writers and their cached authority. Do not mix older and newer writers.
2. Verify replica-set transactions and the retention-first strict index cutover. Preserve unknown jobs, slots and original evidence; investigate duplicate or capacity failures before retrying.
3. Inspect the exact delivery/resource, retain the returned digest and identify the operator and actual drain evidence. Use only an allowed local-stop or original-receipt decision.
4. For migration, verify the scoped policy/environment and actual workload-role access first. Convert only the proven original encrypted credential; coordinate any separate vendor rotation independently.
5. Inspect the permanent completion journal after an uncertain acknowledgement. Keep held resources paused; explicit activation, actual IAM/egress/restore checks and separately authorized pilot evidence remain prerequisites to live rollout.

Configuration and flag checks are process-local. An authorization committed before a later stop can already be in flight, so these transactions do not revoke that call or prove fleet drain. Participating guarded writers share ordering; arbitrary raw/older writers do not. This release adds no global exactly-once guarantee, integration daily budget, automatic CRM reply sync, billing or proxy procurement.

## Verification and remaining work

The final clean main run passes **1,822 backend checks** (1,802 outreach plus 20 account/auth), with 44 historical opt-in drills skipped. All **70 new backend checks** pass: 53 unit/CLI cases, 16 real replica-set cases and one actual standalone denial. Coverage includes concurrent review/migration, journal rollback, late flags/source replacements, lost-ack retry, legacy missing-type/deleted-source stop, persistent holds across disconnect/resave, closed-tenant retention and TTL removal before duplicate-index failure. New-module statement coverage is **94% combined** (control94/review96/migration97/CLI85).

**99 outreach frontend checks** and the production build pass, including the new completed-review/paused-connection message. Python compile, medium/high Bandit, both Compose configuration checks and whitespace checks pass. Existing python_multipart/fork deprecations and dependency/Tailwind/source-map/bundle/unset-key warnings remain. An earlier standalone fixture used an overlong database name and failed cleanup; its bounded name and nested-finally cleanup were corrected, owned leftovers were removed, and the standalone case and complete main run were cleanly rerun. That earlier partial run is not passing suite evidence.

Independent Python review reproduced and closed legacy missing-type backlog omission and disconnect/resave bypass of the hold; the final deleted-source plaintext URL stop/scrub and wider workspace writer checks are approved. The reviewer independently reran 53 final unit/CLI cases and 11 frontend helper cases, and previously checked the 16 replica-set cases. Contract prose was reviewed and its attempt wording corrected to avoid implying a new integration budget charge. No remaining actionable blocker was reported. No new SIGKILL, Redis/Celery redelivery, real AWS/vendor, production IAM, egress, restore or pilot evidence is claimed.

After the final run, the owned replica set had no non-system databases. Its process/storage and owned standalone/final-run test storage were removed; ports 27028, 27029 and 6389 are closed. No Redis service was started. Unrelated dirty files/worktrees are preserved.

Foundations through v2.22 were previously committed/pushed and EC2-deployed at `04ca28b5d1dd7bd213ea67e951970e19fd93bdf3`. The v2.23 integration slice and this v2.24 slice remain local, uncommitted and undeployed. This session changes no production flags/configuration and performs no real AWS/vendor calls, purchases or grants. Default legacy custody and disabled live/generation flags remain unchanged.

Next: remaining Webshare/shared-provider secrets and older campaign-artifact custody, a separate explicit integration activation protocol, and actual workload IAM, process/kernel egress, restore and authorized purchased-proxy/mailbox/voice pilot checks. Different-key/unproven legacy adoption still requires distinct original/vendor-account ownership evidence. The three repository/Desktop v2.24 specifications and all 23 linked release reports byte-match; all 92 local specification links resolve. Pre-edit backup: `/tmp/unravler-docs-before-v2-24-20261008`.
