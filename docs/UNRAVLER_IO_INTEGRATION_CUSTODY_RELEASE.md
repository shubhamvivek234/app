# Scoped integration custody and durable delivery — v2.23

Updated: 2026-10-08. Status: locally implemented and verified; uncommitted and not deployed.

## Outcome and bounded scope

Webhook signing secrets, Slack incoming-webhook URLs and HubSpot private-app tokens now use one configuration/worker boundary. Saves create a fresh credential generation. Opt-in `kms_v1` seals tenant/resource/generation/purpose/environment-bound envelopes; webhook destination and configured HubSpot portal participate in the identity. Default `legacy_fernet` stays unchanged and opens only strict encrypted values on these paths. Plaintext, missing scope, mixed mode, changed policy and cross-workspace substitutions deny without fallback.

Key opening/sealing happens outside retryable Mongo callbacks. Final configuration writes revalidate and write-fence the initiating member or exact REST-hook API key/hash/scopes/expiry, current source and custody policy under the shared workspace guard. Membership/key revocation while sealing cannot install a new destination. Actor-bound configuration and dispatch also transactionally fence the active users row and reject pending/deleted users or a persistent Firebase UID tombstone, even when a shared-workspace membership has not yet been removed. API-key expiry is captured and rechecked after awaited authority/source writes and final save/delete/cancellation steps; expiry aborts the complete transaction rather than leaving partial configuration or cancellation changes. Disconnect cancels known pending work and removes local configuration; it does not prove vendor credential revocation. Role requirements remain webhook:manage, outreach:manage for settings and lead:update for manual CRM synchronization.

This release covers routed configuration endpoints, webhook/Slack event fanout, worker deliveries, test pings and manual HubSpot synchronization. It does not implement HubSpot automatic reply sync: the API reports that capability unavailable, rejects enabling it, and the UI describes manual synchronization without offering the misleading checkbox. A new workspace can enter its required Portal ID and token and submit the configuration. Unused legacy direct-call helpers are outside the new protocol and must not be reused by production entrypoints.

## Durable authorization and evidence

The existing `outreach_webhook_deliveries` collection carries protocol version 2 jobs. New rows contain resource references, captured policy/source digests, bounded event content, actor and optional lead identity. They copy no signing secret, Slack URL, token or credential ciphertext. Stable event/destination/workspace identity recovers an original queued request instead of resetting it. Manual endpoints accept a bounded `Idempotency-Key`; clients that omit it create distinct requests. The UI generates one key per test and never reposts while polling.

Pending work is guard-claimed by one owner for 60 seconds. Decryption occurs outside Mongo, then a snapshot/majority transaction checks that owner, source generation/policy, workspace openness, current permission and request deadline. CRM authorization also captures and write-fences effective lead properties and revalidates the mapping for the configured portal under the shared workspace guard. Mapping ordering covers participating guarded writers; it does not force a write to an existing mapping or fence arbitrary raw writers. The possible-submission marker and attempt charge commit before HTTP. A standalone database cannot authorize HTTP; there is no production transaction fallback.

Manual requests expire after ten minutes; internal event requests after 24 hours. Final HTTP uses the shorter request/owner deadline. Configuration/flag checks are process-local and short-lived authorization can precede a later stop; these checks do not prove fleet drain or instantly revoke already authorized calls. Deployment and erasure must drain all participating writers and cached authority. Raw/older writers are outside the ordering protocol.

| Boundary | Result |
|---|---|
| Interrupted preparation with an expired proven owner | Cancel locally; no key opening or send during recovery |
| Possible submission, missing reply, timeout or interruption | Permanent review hold; no automatic resend |
| Saved original HTTP receipt | Database-only projection recovery; no decryption or network |
| Replaced source, malformed/late receipt or changed projection | Keep saved evidence held; no source adoption |
| Slack HTTP 408/5xx | Review hold after one possible attempt |
| HubSpot HTTP 408/409/5xx | Keep review hold and the lead/portal slot; no second create/PATCH |
| Known permanent rejection | Retain the failed receipt; original work is never reset for replay |
| Signed system webhook HTTP 429/500/502/503/504 | At most six charged attempts with backoff and preserved per-attempt receipts |

Webhook retry is explicitly **at least once**. Receivers must deduplicate stable event/delivery IDs; a server failure is not proof that its application did nothing. Slack and HubSpot have one possible submission per job. A held CRM slot blocks another request for the same lead/configured portal. There is no global exactly-once guarantee across provider accounts, different lead identities or arbitrary raw writers, and no newly implemented common daily integration budget.

Receipts retain only observed HTTP status, local received timestamp and a bounded numeric contact ID for successful CRM responses. Immutable job/source/policy identity, original owner and possible-to-expiry timing bind recovery. Each projected attempt preserves its own owner and original receipt. HTTP acceptance is not evidence of LinkedIn engagement, campaign attribution or remote account ownership. Whitespace-only CRM fields cannot overwrite remote properties with empty strings.

## API, transport and customer behaviour

Webhook test, Slack test and manual HubSpot sync return HTTP 202 with a delivery reference. A workspace-scoped status endpoint exposes an allowlisted result. The UI polls for a bounded period, reports delivery only after a confirmed result, and leaves unavailable/timed-out status pending. Lost POST network/JSON acknowledgements report that the request may still be queued, preserve the generated request key on the error and never silently repost. Review states are visible; the replay control is removed because resetting original evidence is prohibited. Delivery lists exclude payloads, copied secrets, key/policy digests, owner tokens and receipt journals, while retaining an event-type label.

Configuration URL checks are syntax/host/IP checks and never resolve customer DNS in the FastAPI event loop. Provider requests run through one bounded DNS-pinned adapter, with environment proxies and redirects disabled. DNS resolves asynchronously under a timeout, and a pure authorization check runs after resolution and before outbound writes, including after TLS. A denied TLS start closes the socket. Request bodies are capped at 32 KiB and CRM identity responses at 64 KiB, with encoded replies rejected. Oversized or unproven outcomes remain conservative holds; no alternate mutation or 409 fallback runs. Slack credential paths are scrubbed from logging strings, URL objects and nested arguments.

## Retention, erasure and cutover

Startup removes integration/Studio/source-migration/vendor-read evidence TTLs before even the first unrelated mailbox index build; mailbox jobs keep their own retention-first inspection and legacy quarantine. The actual duplicate-index failure case proves these TTLs remain removed when later uniqueness validation aborts. Strict workspace/resource, configured mapping, event/destination and CRM active-slot indexes fail on duplicates rather than hiding conflicts. Event uniqueness includes workspace and provider. Routine startup preserves current v2 jobs.

Old pending/retry/leased snapshot deliveries are quarantined during drained index cutover and runtime. They never dispatch or replay in either custody mode. Their absence of physical receipts cannot be treated as proof of a non-call. Existing old encrypted configuration can remain compatible in legacy mode; KMS adoption needs an explicitly authorized resave/rotation. This release supplies no silent legacy-key/job adoption or bulk secret migration.

Erasure stops and scrubs configuration under the existing workspace protocol. After asserted writer drain, received or unresolved integration evidence becomes a minimal permanent hold containing hashes, outcome and observed timing. Current possible/review states retain their unresolved classification even when a prior webhook retry has an observed receipt; the original receipt digest/timing remains available. Holds carry no event content, destination URL, token, ciphertext or remote contact ID and cannot activate work. Broader product backups, vendor copies, legal retention and actual fleet drain remain separate requirements.

Before rollout:

1. Keep integrations disabled for the cutover process/fleet and drain API, beat, workers and cached writers. Do not run a mixed old/new fleet.
2. Inspect legacy backlog, duplicate configurations/mappings and workspace membership. Preserve evidence before changing indexes; never delete an unknown job to free a slot.
3. Run strict retention/index cutover against a replica set. Startup failure denies release; verify TTL removal and uniqueness rather than bypassing either.
4. Perform any approved settings resave in a controlled database-only maintenance process while delivery writers remain stopped. Scoped mode additionally needs approved KMS policy/environment and real workload-role evidence. Coordinate receiver signing-key rotation explicitly.
5. Finish the drained integration review/migration tools before releasing unknown CRM slots or enabling production recovery. A freshly observed remote fact cannot silently rewrite the original outcome.
6. Verify actual IAM, egress, restore/fleet configuration and separately authorized provider/account checks before enabling a workspace pilot. Restart a single coherent fleet, then observe the bounded pilot under an explicit integrations allowlist.

These are rollout requirements, not actions performed by this implementation session. Prior foundations through v2.22 were already committed/pushed and EC2-deployed as `04ca28b5d1dd7bd213ea67e951970e19fd93bdf3`; the earlier frontend auto-deploy trigger was not an independently confirmed Vercel release. This v2.23 slice changes no production configuration and enables no live actions, provider call, purchase or grant.

## Verification and remaining work

The final clean main run passes **1,752 backend checks** (1,732 outreach plus 20 account/auth), with 44 historical opt-in drills skipped. All **87 new checks** pass: 65 unit/API/adapter cases, 20 real Mongo cases (19 replica-set and one standalone), and two fresh-process SIGKILL cases through the production adapter/state machine over owned loopback TCP. The six delayed authority/source/save/delete/cancellation expiry cases verify complete transaction rollback; three shared-workspace actor-stop cases cover pending deletion, deleted status and persistent UID exclusion while preserving internal fanout. No new Redis/Celery redelivery, live vendor or AWS evidence is claimed.

Current new-module statement coverage is **91%** (custody91/delivery91). **98 outreach frontend checks** pass, including ten delivery-state/POST-ack tests and one rendered new-workspace HubSpot setup test; the production build passes. Python compile, medium/high Bandit, Compose configuration and whitespace checks pass. Existing python_multipart/fork deprecations, dependency/Tailwind/source-map/bundle warnings remain. Earlier old-interface fixtures and a new erasure-test argument-order mistake were corrected before the clean final run; interrupted reruns are not counted as passing evidence.

Independent Python review reproduced and corrected missing final settings authority, Slack replay risk, blocking DNS, configuration-key expiry across awaits, deletion-pending shared-workspace actors and the missing Portal ID form control. The final bounded slice is approved with no remaining HIGH/CRITICAL finding. The reviewer independently verified 65 backend unit/API/transport checks, nine actual Mongo expiry/shared-actor regressions, 11 frontend helper/rendered-form checks, Bandit and whitespace checks. Retry erasure classification, lost POST acknowledgement wording and type annotations were additionally reviewed. Real provider behaviour and production rollout remain unverified.

Next priority: bounded drained integration held-outcome/receipt review and credential migration; then remaining Webshare/shared-provider and older-artifact custody. Actual workload IAM, process/kernel egress, restore epochs/drills, legacy-data validation, broader retention and the purchased proxy/mailbox/voice pilot remain. This slice does not implement automatic procurement/renewal/payment, CRM automatic reply sync or different-key/unproven voice adoption.

The three repository/Desktop v2.23 specifications and this report match. Pre-edit backup: `/tmp/unravler-docs-before-v2-23-20261008`. Owned local database/services and final-run storage are removed after verification; unrelated dirty files/worktrees are preserved. Default legacy custody and disabled LinkedIn/voice live/generation flags remain unchanged.
