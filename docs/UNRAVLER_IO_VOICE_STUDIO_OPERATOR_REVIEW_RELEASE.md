# Unravler.io — Voice Studio operator review

Date: 2026-10-04. Nineteenth bounded local slice, architecture v2.20.0.

## Result and scope

Held Voice Studio clone, preview and delete jobs now have a private, database-only operator review. The two decisions are `stop_local` and `use_receipt`. Both stop current workspace sender/campaign authority and close only the inspected original job's local slot. Neither authorizes another provider request, opens a key/audio envelope, adopts a different credential source, verifies a vendor account or makes a voice usable. No customer-facing resolution endpoint was added.

The review is recorded in the existing TTL-free Studio job. Original owner, possible-call marker, provider source, payload identity and any saved provider receipt remain intact. `operator_local_stop` is separate from `saved_provider_receipt`; a local stop cannot turn an unknown call into a successful or rejected provider outcome. Input/result ciphertext is scrubbed. Physical daily allowances are not refunded, and unrelated delivery tokens/owners remain held.

## Exact inspection and authority ordering

Inspection exposes only allowlisted job/profile identifiers, status, original outcome, a private snapshot digest, blockers, allowed decisions, source-current boolean and affected-row counts. It excludes provider IDs/source hashes, custody material, audio and operator narratives. The digest privately binds the complete original job/profile and captured configuration metadata, along with bounded current workspace Studio jobs, queued/claimed/generating campaign voice preparations, accounts, active/warming campaigns, sender execution and permission rows. Each family is capped at 100; exceeding a cap denies instead of silently omitting authority.

Resolution requires all three live/Studio/campaign-preparation flags off, an exact inspection digest, identified operator and drain evidence. Original worker ownership/binding digests must be proven and its lease expired. Other pending Studio writers, live sender leases or unrecovered claimed/generating campaign preparations block review. Profile/source/resource replacement blocks local cleanup. Consent changes preceding a fresh inspection are retained; review never renews consent.

One snapshot/majority transaction uses the existing stable workspace suppression guard and writes the matching read authorities. It revalidates inspection, pauses current senders and active/warming campaigns, disables auto-launch, increments campaign authorization revisions, latches existing sender execution/permission authority and cancels queued campaign audio preparations. Only then does it remove or update the exact original profile and save the terminal review. Physical tokens and owners are preserved. An open workspace can receive missing stopped sender authorities for its existing accounts; a closed erasure workspace never recreates them or installs a clone/preview receipt.

Profile cleanup and the journal commit with the authority stop. Transaction abort leaves all changes absent; concurrent identical reviews and lost commit acknowledgements reuse the same saved journal without repeating pauses/revisions. A conflicting operator/decision/evidence/digest denies. Original receipt arrival before review invalidates the old unknown inspection; a saved review's terminal state prevents a late worker from projecting another receipt. These guarantees cover participating current writers. All-writer/cache drain and operator identity are trusted private-host assertions, not automated drain detection or an authentication certification.

## Decision semantics

| Original operation/evidence | `stop_local` | `use_receipt` |
|---|---|---|
| Proven preparing clone with no possible-call marker or receipt | Remove only the original local placeholder and release its local profile quota | Denied |
| Unknown clone | Retain unavailable placeholder/quota and original unknown evidence; close only its local job slot | Denied |
| Clone with a valid original saved receipt | Retain unavailable local profile and receipt evidence | Attach the original received remote ID for custody only; retain review-required/vendor-verification/consent-revoked state |
| Preview | Retain profile/evidence and scrub audio; no playback or regeneration | Valid original preview metadata may close the local slot, without opening/playing/regenerating audio |
| Delete | Retain local profile for unresolved cleanup; no vendor deletion claim | Remove only the original local profile using its valid original confirmed deletion receipt |

Saved receipts require original owner and possible/received timestamp ordering, plus the operation's bounded remote-ID, deletion or audio-digest contract. Malformed receipts deny rather than inventing an outcome. Missing profiles can receive a local stop; clone/preview receipt installation requires the original local profile. A confirmed delete can finish without creating a missing profile. Replacement profiles/remote assets remain untouched.

Surviving profiles receive persistent `studio_review_required=true`, independent of display status. Campaign profile use, new preview/delete work and consent renewal deny while this latch remains. Consent withdrawal remains available. Revoked consent/status takes precedence even when a clone receipt says vendor verification is needed; the original verification requirement remains in its receipt. Clearing this latch and proving source/remote identity require a separate future protocol. Current provider-key possession is not proof of vendor account identity.

Erasure retains minimal original unresolved/received evidence and the review's provenance, decision, time, digest and hashed operator/evidence/owner identifiers. Terminal `review_stopped` cannot erase the original unknown outcome. Narrative, plaintext/ciphertext audio, keys and replay permission are excluded from retained holds. No provider revocation/deletion, remote backup retention or whole-product erasure guarantee is added.

## Private operator procedure

Use the trusted private operations host and existing database configuration. Keep flags disabled; pause and drain every workspace API, media, campaign, Studio/consent/profile, mailbox, sender, integration, suppression, connection and erasure writer and its cached authority. Recover live claimed/generating preparations using their existing conservative protocol first. Verify replica-set transaction support and strict TTL-free Studio indexes. Inspect original provider/owner evidence privately; the CLI's labels do not prove the drain occurred.

```bash
python -m outreach.ops.pilot inspect-studio-review \
  --workspace <workspace-id> --job <studio-job-id>

python -m outreach.ops.pilot resolve-studio-review \
  --workspace <workspace-id> --job <studio-job-id> \
  --decision stop_local --operator <operator-id> \
  --evidence "Private audit reference and complete writer/cache drain evidence" \
  --review-digest <exact-inspection-digest> \
  --workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES
```

`use_receipt` is the only alternative decision and requires the original valid saved receipt. Do not place credentials, provider IDs, audio or sensitive narrative in CLI arguments/drain evidence. Commands return sanitized JSON and perform no provider/KMS HTTP. Retry a lost acknowledgement with the same original decision/operator/evidence/digest; conflicting reviews deny. Do not interpret `review_completed` as permission to use or reactivate the voice. No production review was run in this slice.

## Remaining boundaries

This supersedes earlier held-outcome/received-review gaps only for the two bounded local decisions. Explicit source adoption, legacy profile adoption, vendor verification and review-latch release remain separate. Other vendor/shared-provider/Webshare credentials, older campaign artifacts, integration boundaries, actual workload IAM/process isolation/kernel proxy-only egress, restore fencing and broader retention remain unfinished. Separately authorized purchased IPRoyal/mailbox/voice pilot evidence is still required. Manual verified-invoice provisioning remains; automatic billing/proxy procurement is deferred.

Configuration checks are process-local and require drained fleet/config/cache cutover. Already authorized/in-flight calls and older/raw writers outside the shared guard are operational limits; this is not global credential revocation. Default `legacy_fernet` and disabled live/generation/Studio flags remain. No commit, push, deployment, AWS/vendor call, purchase or production grant occurred.

## Verification and delivery

Nineteenth-slice verification: the final clean main run passes 1,491 backend checks (1,471 outreach plus 20 account/auth companions), with 44 historical opt-in drills skipped. All 67 new checks pass: 42 service cases, eleven private CLI cases and fourteen real Mongo cases (thirteen replica-set plus one standalone denial). The new review service has 95% statement coverage. Compile, medium/high Bandit, both Compose configurations, whitespace checks and independent Python/code/report review pass. Frontend code is unchanged; the earlier 93 tests/build remain historical evidence. New review tests perform no vendor/key HTTP; existing prior loopback cases run in the main suite, without adding Redis/SIGKILL/live-provider/IAM/egress/restore proof. Initial temporary namespace-fixture failures were corrected before the clean final run. Existing python_multipart/fork deprecations and unset ENCRYPTION_KEY Compose warnings remain.

Cleanup and delivery: temporary databases were absent; owned replica/standalone Mongo storage was removed and ports 27028/27029/6389 are closed. No Redis was started. All three repo/Desktop v2.20 specifications and their 80 relative report links/19 unique supporting reports match. Pre-edit backup: /tmp/unravler-docs-before-v2-20. Unrelated services/worktrees and prior dirty files were preserved. Local only: no commit, push, deployment, AWS/vendor call, purchase or production grant; legacy custody and disabled live/generation/Studio defaults remain.
