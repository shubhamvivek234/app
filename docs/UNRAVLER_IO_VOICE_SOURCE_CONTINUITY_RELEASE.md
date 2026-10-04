# Unravler.io — Voice source continuity

Date: 2026-10-04. Twentieth bounded local slice, architecture v2.21.0.

## Result and scope

Private source review can now migrate an existing Voice Studio profile from a recorded legacy key fingerprint or older scoped envelope to the currently configured scoped envelope, but only when both original and destination material open to the exact same key. The migration roots the profile's remote identity in an original valid clone receipt, stops current workspace sender/campaign authority and saves a permanent metadata journal with the new source and a persistent profile review hold. It does not contact ElevenLabs, open audio, rewrite original Studio receipts, change consent, verify a vendor account or release the review hold.

This proves stored-key continuity. It does not prove current vendor account ownership, allowed-voice permissions or completed vendor verification. A different key cannot pass equality even if an operator asserts that it belongs to the same account. A profile without its recorded source and original clone evidence cannot be adopted. Those cases require a separate future vendor-evidence protocol. The two nineteenth-slice held-job decisions remain distinct and retain their original provenance.

## Original evidence and exact inspection

The profile must have a bounded non-mock remote ID, integer revision, dictionary consent record, proven source and a supported non-running status, with no Studio job lock. An original completed clone, or an exact `review_completed`/`use_receipt`/`saved_provider_receipt` review with received outcome, must match the profile's derived local identity and remote ID. Original owner, source/content/configuration digests, possible/received ordering and the clone's boolean verification receipt must remain proven. Unknown original work or any original confirmed delete blocks migration; ownership and malformed records cannot trigger key opening.

Later same-key rotations follow permanent migration lineage back to that same original clone digest and remote-ID digest. The normalized root digest survives naive/aware UTC BSON decoding. Original jobs/receipts are read and write-fenced, with their source and physical evidence preserved. A lineage journal never fabricates a different clone, relabels an old delivery outcome or assigns a new remote asset.

Inspection returns only allowlisted workspace/local-profile identifiers, digest, blockers, availability, original-clone/source-current booleans and affected sender/campaign counts. It does not decrypt, return the remote ID/source hash, expose a key/envelope, or include operator narratives. Its private digest binds the complete profile, original profile jobs, migration lineage, current key configuration metadata and all bounded authority rows. Each family is capped at 100. Pending Studio writers, claimed/generating campaign preparations, live sender leases, closed tenants, malformed identities, unavailable scoped configuration and capacity gaps deny.

## Custody proof outside transactions

Destination mode must be `kms_v1`; the default remains `legacy_fernet` until a separately authorized drained cutover. Original legacy input uses the exact deployed `elevenlabs` fingerprint. Original scoped input uses its exact envelope/generation under the current configured environment and purpose. Wrong original source, generation, purpose/environment, unavailable old key custody, mixed configuration or downgrade deny without fallback. Scoped-to-scoped continuity does not silently cross custody environments or invent missing historical proof.

The first snapshot/majority workspace transaction revalidates inspection and write-fences the matching authorities before the private original-input callback is invoked. The callback reads bounded hidden/explicit-stdin legacy input or a private original-envelope file. Original and destination key opens happen outside Mongo callbacks; constant-time equality is mandatory. Complete destination storage/generation/environment/KMS/workload policy is rechecked across awaits and at installation. Key opening failures or mismatch produce no source update, journal, provider request or Studio budget change. Key services in tests are local fakes; no real AWS request was made.

Plaintext exists transiently in the private operation's Python objects. It is excluded from representations, database records, broker/public output and error messages, but zeroization/process isolation is not guaranteed. File ownership checks and operator labels do not certify actual workload IAM. Configuration checks are process-local; actual fleet/config/cache drain remains required.

## Atomic stop, source installation and retry

The final snapshot/majority transaction uses the stable workspace suppression guard and write-fenced read authorities. It checks the exact original inspection, current key material/policy and disabled live/Studio/preparation flags again. Current senders/campaigns are stopped first, auto-launch disabled and campaign authorization revisions incremented. Existing execution/permission rows are latched while preserving unrelated physical tokens and owners; queued campaign voice preparations are cancelled without refunding physical allowances. Source review cannot resolve an unrelated delivery hold.

Only the exact original profile revision/source/remote identity is updated. Its source becomes the prepared scoped configuration, revision increments, and `studio_review_required=true` persists. Consent and account assignments stay intact. Revoked consent retains `consent_revoked`; an existing pending status or original verification-required receipt retains `needs_vendor_verification`; other supported states become `review_required`. The hold independently denies use, preview/delete and consent renewal. A source migration never clears it or resumes a campaign. Changed revision/source/status invalidates old campaign clips/content approvals without rewriting old artifact identities or receipts.

The profile update, stopped authority and permanent `same_key_continuity` journal commit together. Failure of the final journal insert rolls them back together. The journal contains before/after source hashes, configuration/inspection/remote/root-clone digests, resulting revision/profile identity, operator/drain evidence and time; no key/envelope/audio/remote ID is stored there. Existing owner/receipt/possible-call evidence remains unchanged. Concurrent identical reviews and acknowledgement loss reuse the same journal without rereading original input, opening keys or stopping authority again. Conflicting operator/evidence denies. A later replacement/configuration change yields `current_matches=false` on a saved retry and is never overwritten.

Closed erasure workspaces deny this operation, including before original-input/key opening. Erasure classifies the new collection, purges its private journal and retains only minimal continuity/source/root/remote/review/profile digests, hashed operator/evidence identifiers, provenance and time. Narrative, custody material, activation/replay permission and remote-cleanup claims are excluded. Existing minimal original submission and remote-cleanup retention continues separately.

Startup removes destructive TTL indexes from both Studio jobs and source journals before the relevant strict builds. The journal has a unique workspace/profile/inspection identity and a bounded-lineage index; uniqueness errors are not ignored. Actual transaction/index verification and all-writer/cache drain remain rollout requirements, including old erasure writers that do not yet recognize the collection.

## Private operator procedure

Use the trusted private operations host with existing Mongo configuration. Keep all live, Studio and campaign-preparation flags off. Drain every workspace API/media/beat/campaign/Studio/consent/profile/integration/transport/mailbox/connection/suppression/erasure writer and cached authority. Recover active claimed/generating preparations through their existing conservative protocol. Resolve pending Studio work with its existing evidence-bound review first; unknown/deleted profile outcomes cannot be forced through source migration. Operator identity and drain acknowledgement are assertions, not automated authentication/drain detection.

```bash
python -m outreach.ops.voice_source_review inspect \
  --workspace <workspace-id> --voice <local-profile-id>

python -m outreach.ops.voice_source_review migrate \
  --workspace <workspace-id> --voice <local-profile-id> \
  --operator <operator-id> \
  --evidence "Private audit reference and complete writer/cache drain evidence" \
  --review-digest <exact-inspection-digest> \
  --workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES
```

The default prompt reads the original legacy key without echo; explicit `--prior-key-stdin` uses the bounded existing private reader. The key is never a CLI argument and there is no echoed-prompt fallback. For an original scoped envelope, add `--prior-envelope <private-original-envelope-file> --prior-generation <original-generation>`. The descriptor-based reader rejects symlinks, public/foreign-owned files, non-regular files, oversized/non-ASCII/whitespace input and plaintext; it neither rewrites nor installs the file. Argparse/runtime failures suppress private argument/provider/file details. Do not place secrets or sensitive narratives in workspace/operator/evidence arguments.

Commands return sanitized JSON and perform no vendor HTTP. Saved retry uses the same original operator/evidence/digest and skips all secret input. No customer endpoint or `activate`, vendor-verification, different-key adoption or replay command was added. Migration leaves sender/campaign permission and profile review stopped; later vendor evidence and review-latch release need a separate protocol. No production migration or configuration installation was performed.

## Remaining boundaries

This supersedes source-adoption gaps only for proven same-key storage continuity with original clone evidence. Different-key source adoption, unproven legacy profiles, vendor ownership/permissions/verification, and explicit review-latch release remain next. Other shared/provider/Webshare and older campaign-artifact custody, actual IAM/process/kernel egress, restore fencing, integration/retention boundaries and separately authorized purchased IPRoyal/mailbox/voice pilot evidence remain. Verified-invoice provisioning stays manual; automated billing/proxy procurement is deferred.

Already authorized/in-flight work and older/raw writers outside the guard require operational handling. This is not global credential revocation, vendor deletion or whole-product erasure. Defaults and flags remain unchanged. Local only: no commit, push, deployment, AWS/vendor call, purchase or production grant.

## Verification and delivery

Twentieth-slice verification: the clean final main run passes 1,563 backend checks (1,543 outreach plus 20 account/auth companions), with 44 historical opt-in drills skipped. All 72 new checks pass: 47 service, 12 private CLI and 13 actual Mongo cases (12 replica-set plus one standalone denial). The two new modules have 93% combined statement coverage (service 94%/CLI 90%). Independent review reran 101 service/CLI/existing-review cases and approved code/report; compile, medium/high Bandit, both Compose configurations and whitespace checks pass. Frontend unchanged; prior 93 tests/build remain historical evidence. New checks use local fake key services/provider results and no AWS/vendor HTTP. Prior loopback cases rerun in main without new Redis/SIGKILL/IAM/egress/restore proof. Five binding/status/malformed-record regressions were reproduced and fixed before the clean final run. Existing python_multipart/fork deprecations and unset ENCRYPTION_KEY Compose warnings remain.

Cleanup and delivery: temporary databases were absent; owned replica/standalone Mongo storage was removed and 27028/27029/6389 are closed. No Redis was started. All three repo/Desktop v2.21 specifications and 83 relative report links/20 unique supporting reports byte-match. Pre-edit backup: /tmp/unravler-docs-before-v2-21. Prior dirty files, unrelated worktrees and services were preserved. Local only: no commit, push, deployment, AWS/vendor call, purchase or production grant; default legacy custody and disabled live/generation/Studio flags remain.
