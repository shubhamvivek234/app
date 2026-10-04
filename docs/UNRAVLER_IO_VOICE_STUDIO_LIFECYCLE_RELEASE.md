# Unravler.io — Voice Studio lifecycle and consent

Date: 2026-10-04. Seventeenth bounded local slice, architecture v2.18.0.
Local implementation only; no commit, push, deployment, real vendor/AWS call, purchase or production grant. Live actions and campaign generation retain disabled defaults. `OUTREACH_VOICE_STUDIO_ENABLED=false` is a separate default for clone/preview/delete calls.

## Implemented behavior

Voice Studio API requests now create durable MongoDB jobs rather than performing synchronous provider calls. Stable workspace/actor/operation/request identities reject changed payload reuse and recover committed insert acknowledgements. The browser preserves request identities for retries. Queued clone placeholders count toward the five-profile limit, including unknown outcomes. Existing profiles without consent/source proof are unavailable for campaign voice use; user consent cannot invent legacy provider custody.

Clone requests record the identified actor's explicit assertion that they are the speaker or have permission to clone/use the voice. This is an assertion, not verified speaker identity or vendor verification. Samples must be actual mono 16 kHz, 16-bit PCM WAV, 20–60 seconds, within the decoded/raw bounds. Browser recordings retain their actual recorder MIME and are decoded/resampled before upload, rather than being relabelled WAV. Browser source uploads are capped at 10 MB; the route collects only a size-bounded request body before multipart parsing, rejects declared/chunked oversize before temporary-file construction, and the endpoint reads only the bounded WAV allowance. Names and finished preview scripts are bounded.

Profiles bind the original ElevenLabs credential fingerprint. This is a frozen credential-source identity, not proof of a verified vendor account. Key changes cannot silently adopt existing profiles. Current consent, profile revision/status/provider identity and source enter campaign content bindings; withdrawal and delete/cancel revisions invalidate prior clips/approvals. Consent withdrawal is permitted while work is held and while Studio calls are disabled; possible/received evidence and ownership remain. Delete permits source-proven revoked/verification-pending profiles, is unavailable during active campaign TTS, and preserves the original state when a proven pending deletion is cancelled. Replacement provider resources are retained for review instead of being deleted by old cleanup.

The worker operates on job/workspace references on the media queue. Celery results contain only job ID/status, never input/audio ciphertext or remote evidence. Fair publication reserves due timestamps before broker access; broker failure retains queued work. Recovery and content cleanup run with flags off. Evidence, requests and held slots have no TTL. Queued/preparing work expires and stops under its original fifteen-minute authorization deadline/two-minute lease; possible submissions cannot be reclaimed by lease expiry. Unknown outcomes retain profile ownership and require operator review; this slice does not provide a human outcome-resolution/adoption command.

## Authorization and physical boundary

Workspace suppression guards order participating writers and all Studio changes. Snapshot/majority transactions revalidate current actor membership/role, paid term (clone/preview), profile/job ownership, original configuration/source and deadlines. Membership, entitlement and applicable profile authority rows are written to conflict with concurrent changes. Provider HTTP and KMS work run outside retriable database callbacks. The possible marker and UTC-day budget commit together: five clone, twenty preview / 20,000 preview characters, ten delete calls per workspace/day. Possible calls are conservatively charged without automatic refunds.

The adapter allows exactly one bounded fixed-endpoint HTTP request with captured credentials, no retries, redirects, ambient proxy configuration or mock fallback. It rechecks captured configuration/deadline before transport, rejects encoded responses before decoding and reads bounded raw streams. Preview is returned as validated PCM WAV. Clone receipts retain the remote ID and vendor verification state; verification-required profiles remain unusable. Delete requires the documented successful JSON `status: ok`, rather than assuming missing/404/empty responses establish deletion. Unused legacy real-call helpers now deny and retain only test mock behavior.

Known clone/delete receipts commit under the original owner even if current paid/consent/source authority is lost after HTTP; projection remains held. Valid preview response metadata also survives content-encryption failure without playback or another paid call. Original received evidence is distinct from unknown outcomes. Saved receipts recover database projection without HTTP. Late matching receipts may improve an interrupted hold, but cannot replace another owner or authorize changed profiles.

Provider contract references: [instant clone](https://elevenlabs.io/docs/api-reference/voices/ivc/create), [speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), [delete](https://elevenlabs.io/docs/api-reference/voices/delete). These references describe wire contracts; local tests do not verify account capability, model availability or real audio quality.

## Custody, playback and erasure

Studio samples, scripts and cached preview audio use authenticated encrypted blobs bound to workspace/job/payload digest/input-or-result purpose. Legacy Fernet remains the default. Opt-in KMS wraps per-content AES-GCM data keys under the distinct `voice_studio_key` purpose, job/resource generation and configured environment; downgrade, context swapping, malformed or oversized content deny. This does not migrate the ElevenLabs API key or older campaign artifact custody.

Inputs are scrubbed after receipt, unknown hold or proven stop. Cached previews expire after 24 hours through exact-value content cleanup, retaining job/receipt identity. Playback rechecks current workspace/role/paid/profile/source context before and after opening, validates actual WAV content and its original receipt digest. API DTOs exclude scripts, samples, ciphertext, consent actor/assertion detail, provider IDs/source hashes and private errors.

Outreach erasure now includes Studio jobs/budgets, cancels proven pending work and scrubs content at stop. Drained purge retains minimal unknown/received evidence and remote voice cleanup IDs/source references. It does not call the vendor or claim remote voice/sample deletion. Retention/legal basis, remote copies/backups and whole-product erasure remain separate. Stop/drain evidence is an operator assertion.

## Verification

1,363 distinct backend checks pass: the clean main run passed 1,356 (1,336 outreach +20 account/auth companions), with 44 historical opt-in drills skipped; seven later receipt-encryption/SIGKILL/production-codec/ingress regressions also pass. There are 56 new checks, including eleven actual Mongo cases. The current 69-test focused run passes and measures 91% combined statement coverage (service90/custody98/adapter94); all 78 affected campaign/review/API consumer checks pass.

The two fresh-process SIGKILL cases use the production adapter over bounded loopback TCP: an HTTP response without a saved receipt stays held; a saved receipt repairs without another call. Concurrent real workers make one call; request-insert acknowledgement loss returns the same job. Production-default naive UTC decoding is tested for clone, preview and exact saved playback. These are local fault/transport checks, not new Redis/Celery broker-redelivery or actual standalone/vendor checks.

All 93 frontend tests in 21 suites and the production build pass. Python compile, Bandit, Compose config, diff checks and final independent Python review pass. Build retains existing dependency/Tailwind/source-map warnings; tests retain existing multipart/fork warnings. The initial missing-module red run, old fixture assumptions, default-codec bug and sub-millisecond fixture mismatch were corrected and rerun. No real provider credits or AWS operations are involved.

## Cutover and remaining work

Keep all provider/live flags off. Drain older API, media, integration, transport, campaign voice, consent/profile, connection, suppression and erasure writers; old synchronous clients cannot remain during rollout. Verify replica-set transactions, run the strict Studio indexes (duplicates/conflicts fail; destructive job TTLs are removed), review legacy profiles and unknown slots, and deploy the compatible API/media/beat/UI versions together. Configuration rechecks are process-local: fleet/config/cache rotation and actual workload IAM/kernel egress require operational proof.

Next: scoped ElevenLabs/vendor/shared-provider/Webshare credentials and older voice artifacts; drained Studio unknown-receipt resolution/legacy source adoption and vendor verification where needed; integration event/transport boundaries, actual IAM/process isolation, kernel egress, restore epochs, broader retention and separately authorized purchased IPRoyal/mailbox/voice pilot checks. Automated billing/proxy purchase/renewal remains deferred.

Cleanup: no temporary databases remained; owned Mongo/storage are removed and ports 27028/6389 are closed. No Redis was started. Unrelated services/worktrees and prior dirty files were preserved. All three repo/Desktop v2.18 specifications and their supporting reports match; pre-edit backup /tmp/unravler-docs-before-v2-18.
