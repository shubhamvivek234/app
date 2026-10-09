# Unsubmitted Studio input stop and scrub — v2.33

Updated: 2026-10-08. Status: locally implemented and verified. Uncommitted and not deployed.

## Result and original proof

A private reviewed maintenance workflow stops recognized **unsubmitted** Voice Studio clone or preview jobs and removes their encrypted recording/script input. It opens no ciphertext or key and calls no vendor. It does not convert an input to new storage, resume a job, refund a budget, assert vendor deletion, grant consent or activate outreach. Short-lived original execution authority is never extended or relabelled.

Eligibility requires an exact workspace/job identity, original SHA-256 payload/configuration/profile/provider-source bindings, bounded original actor/name/character metadata, native BSON-millisecond timestamps and the original at-most-15-minute authorization interval. Only the known original job fields are accepted. Queued jobs must have no owner or lease; preparing jobs require an identified original owner and a proven expired native lease bounded by the original deadline plus the two-minute claim interval. An expired authorization interval can be stopped. Any possible marker, receipt, result, alternate plaintext/input field, unknown job schema, live/unproven owner or held outcome denies this path.

Input storage recognition accepts existing bounded Fernet or scoped Studio envelope prefixes. **It does not authenticate or open that input.** The review proves local job-protocol metadata and current profile ownership; it is not cryptographic content verification or independent vendor attestation. Participating workers commit their possible-call marker and physical budget before HTTP. Arbitrary raw writers or an undrained older fleet remain outside that ordering, so recognized metadata alone cannot prove those processes made no call.

The full local profile must still match the captured original profile identity, source, voice ID and Studio job slot. A clone additionally requires the exact derived local placeholder ID, creating state, revision one, original name/native dates/recorded consent, empty assignments and only the known placeholder fields, without a remote voice. Its original consent assertion binds actor, payload, version and creation time. Only this proven unused placeholder is removed. A preview must retain the original current active resource, consent, revision and absent review hold. It keeps vendor resource, consent, status and assignments; the slot is cleared, revision advances and an independent review latch blocks new use. Changed/revoked/replaced profiles deny this cutover and remain available to separate review or erasure protocols.

## One guarded transaction

Inspection is metadata only. It returns original workspace/job references, blocker names, affected sender/campaign counts, normalized SHA-256 review digest and `activation_allowed=false`. The digest captures the full target job/profile, existing stop history, workspace closure, current custody-policy digest and bounded Studio/preparation/sender/campaign/execution/permission authorities. Each authority collection is limited to 100 rows; capacity or sender-identity ambiguity denies.

Applying the stop requires identified operator, separate lowercase SHA-256 evidence, that exact inspection digest, all four outreach/integration/Studio/voice-preparation gates disabled and an explicit all-workspace-writer/cache drain acknowledgement. This is an operator assertion; the command does not inspect the real fleet or clear caches. Current provider keys need not be usable because none are opened. Custody mode/environment/KMS policy are captured and must stay unchanged during a new stop; no destination mode is installed.

Snapshot/majority workspace-guard ordering fences target and existing authority rows. The transaction first pauses senders and active/warming campaigns, disables auto-launch, advances campaign authorization revisions, latches permissions and cancels known queued campaign recording preparations. It preserves physical owners/tokens/leases, paid budgets, receipt history and unrelated uncertainty. Live/unproven sender work or claimed/generating campaign work denies. Other recognized unclaimed queued clone/preview jobs can be stopped separately; the command leaves their inputs intact. Other preparing/possible/received work and live or unproven held leases deny; expired held outcomes remain unchanged.

Within that same transaction the exact original placeholder is deleted, or the exact preview profile is latched and its job slot cleared. Full original job CAS sets `review_stopped`, updates the local stop timestamp and unsets only `input_enc`; original payload/source/configuration/owner/lease/consent/timing identity remains. The exact stopped row is checked and a permanent metadata journal is inserted atomically. A pure policy/disabled-gate check follows all awaited readbacks and receipt work immediately before callback completion. Commit can follow; this is process-local configuration proof, not fleet/clock consensus or kernel enforcement.

Unsupported standalone Mongo denies before stopping, deleting a profile or scrubbing input, with no fallback. Job/profile/authority/journal failures roll back together. No separate preflight leaves an earlier partial stop in this workflow because no outside key work is necessary.

## Retries and retention

Journal identity binds workspace/job/original inspection; request identity additionally binds exact operator and evidence. Ordinary and guarded concurrently saved exact receipts precede original-source inspection and repeated stopping. Lost acknowledgement returns historical `review_stopped`, current-job comparison and activation false. A false match reports replacement or removal; it never cleans up that newer state. Changed review/operator/evidence cannot reuse the receipt. Same-ID queue/worker deliveries cannot replay the terminal job; new work remains subject to ordinary separately authorized creation and review.

The TTL-free `voice_studio_input_stop` journal uses the existing credential-migration collection. It contains original job/profile/material/consent/owner/operator/policy digests, original operation/status, separate evidence digest, stop time and `unsubmitted_studio_input_stop` provenance. It contains no audio, script, ciphertext, raw vendor voice, cookie or raw operator. Stop attribution in existing execution permissions remains part of their existing private authority audit. This journal is local protocol review evidence, distinct from provider receipts or vendor withdrawal confirmation.

Strict partial unique workspace/job indexing runs after retention-first startup; duplicate original history fails startup rather than being silently discarded. Erasure retains minimal hashed `voice_studio_input_stop` provenance and purges ordinary jobs/journals/content. After purge, a permanently closed tenant cannot recreate job/profile/permission state through this path. Remote cleanup, legal retention, backups and restore remain separate.

Implementation: `outreach/core/voice_studio_input_cutover.py`, private `outreach/ops/voice_studio_input_cutover.py`, new partial index in the existing recording-migration helper and minimal retention in `outreach/core/erasure.py`. Existing Studio producers, crypto, consumer API and UI are unchanged.

## Private procedure

Retain original job/profile/protocol evidence independently. Disable all four gates and pause/drain every workspace writer and cache. On the trusted backend host:

```text
python -m outreach.ops.voice_studio_input_cutover inspect --workspace WORKSPACE --job ORIGINAL_JOB_SHA256
```

Review every blocker and retain the exact digest. Stop only the eligible original unsubmitted job:

```text
python -m outreach.ops.voice_studio_input_cutover stop --workspace WORKSPACE --job ORIGINAL_JOB_SHA256 --operator OPERATOR --evidence-digest REVIEW_EVIDENCE_SHA256 --review-digest INSPECTION_DIGEST --workers-drained I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES
```

Only references/digests are accepted; no audio, script, password, source, replay or activation inputs exist. Parser/runtime errors are sanitized, and the client closes on database-selection failure. Preserve original evidence and the exact saved receipt. Resolve stale inspections or unknown outcomes separately; do not enable gates to force a stop. See the [operator guide](OUTREACH_PROXY_PROVIDERS.md).

## Verification

All **92 new focused cases** pass in **69.28 seconds**: 62 service/proof cases, 11 CLI cases, 18 actual replica-set cases and one actual standalone denial. Dedicated new-module statement coverage is **97% combined** (service97/CLI98). Actual database checks cover native default UTC BSON, exact literal-array profile CAS, retained physical owners/tokens/budgets, queued and expired-preparing stops, preview consent/resource preservation and review latch, four rollback points, stale original/authority snapshots, final awaited-readback policy/gate rollback, lost-ack/concurrent saved receipts, independently stopped queued siblings, minimal closed-tenant erasure, retention-first strict unique indexing and standalone denial.

Tests were written first and initially failed on the absent module. The shared fake treats all literal-array queries as scalar membership; the new fixture isolates exact-array matching for full original CAS without changing production behavior or the shared fake. The scoped-input test initially lacked its imported fixture and then mocked a nonexistent key helper; the fixture and mock were corrected to the actual custody object's open method, and both isolated scoped cases pass. The clean final 92-case run includes every corrected test. Production source was unchanged during these fixture corrections; initial failures are not green release evidence.

Independent initial source/CLI/index/erasure review approves the scope, with 125 focused/affected cases passing. Independent final source/Mongo-test-contract review and 73 current unit/CLI cases pass; the reviewer inspected actual database tests without running services. Contract review corrected one sibling held-lease wording detail, with no source defect. Compilation, medium/high Bandit, development Compose, production Compose (the existing symlink) and whitespace checks pass with existing warnings. Frontend unchanged; earlier 99 frontend tests/build are historical. The final complete normal outreach/account-auth suite passes **2,441 backend checks** (2,421 outreach plus 20 account/auth), with **44 historical opt-in skips** and two existing warnings, in **763.84 seconds**. All 92 new cases are included; no failing case is excluded and no production source or crash-test timeout was changed during the full run. Broad tests run without coverage; dedicated new-module coverage preserves the pre-existing repository cache and avoids the instrumented subprocess interaction disclosed in v2.29. No new HTTP, SIGKILL, Redis, broker-redelivery, real KMS/AWS/vendor or real fleet evidence is claimed.

Zero owned temporary databases remained after verification. Exact PID/command/root ownership was validated; the Mongo process/storage and explicit final test directory are removed, with ports 27028/27029/6389 closed. No Redis was started. Diagnostic logs and explicit temporary coverage remain; pre-existing repository cache and unrelated dirty files are preserved. Three v2.33 repo/Desktop specifications, the runbook and all 32 linked release reports byte-match, with 119 local specification links verified.

The pre-edit backup contains eight matching v2.32 repo/Desktop specification/runbook copies in `/tmp/unravler-docs-before-v2-33-20261008`. No production configuration/database, IAM, real provider call, purchase, payment grant, custody default or flag changes. v2.23–v2.33 remain local, uncommitted and undeployed.

## Remaining work

Older synchronous samples, absent/unknown original-job proof, possible/held Studio outcomes and unproven/expired recording custody need separate evidence or existing recovery/erasure paths. This slice stops eligible pending inputs; it does not claim to migrate them or complete whole-product sample deletion. Missing-original-fact Webshare adoption, remaining shared-provider credentials, explicit integration activation, different-key/unproven voice evidence and actual IAM/temporary-role/kernel-egress/backup-restore/authorized-pilot checks remain outstanding.
