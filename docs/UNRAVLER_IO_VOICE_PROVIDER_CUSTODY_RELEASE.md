# Unravler.io — Voice provider key custody

Date: 2026-10-04. Eighteenth bounded local slice, architecture v2.19.0.

## Result and scope

Voice Studio clone/preview/delete and offline campaign audio preparation now use an operation-local prepared ElevenLabs key. API/configuration/profile/content-binding inspection uses synchronous metadata and never opens this key. Workers open custody outside Mongo transaction callbacks before the physical marker and paid-call reservation, then validate the captured configuration before authorization, after commit and at the production adapter's client entry. Only the HTTP header receives plaintext; Mongo jobs, broker references, public DTOs and normal representations exclude it.

The key is a shared application credential, scoped separately from tenant-specific Studio audio, mailbox tokens and LinkedIn sessions. Opt-in `kms_v1` binds the `voice_provider_key` purpose to the reserved `outreach-voice-provider`/`elevenlabs` resource, operator-supplied generation and configured environment. Existing KMS/AES-GCM integrity, pinned-key and frozen temporary-workload-role checks apply. Actual AWS policies and process isolation remain unverified. Wrong purpose/generation/environment, malformed envelopes, mixed real plaintext configuration and downgrade deny; there is no plaintext fallback.

Default `legacy_fernet` mode retains the existing environment key and its exact legacy source fingerprint. This compatibility name does not imply that the legacy environment key is encrypted. Scoped envelope/generation configuration in legacy mode denies. The existing Studio, campaign-generation and live-action flags retain disabled defaults.

## Captured authority and rotation

New campaign jobs persist only a private configuration digest alongside the existing content/profile/source binding. Scoped jobs without that proof deny before key opening or budget reservation. Legacy jobs can retain the earlier legacy fingerprint contract. Studio jobs retain their existing source and exact configuration proofs; the old legacy digest is unchanged. Prepared keys validate value integrity and the complete current storage/generation/custody policy locally at the final adapter boundary. Changing key storage, mode, environment or pinned KMS/workload settings invalidates the prepared value.

Encrypted source fingerprints deliberately include the exact envelope/generation/environment. A replacement or rewrapped envelope invalidates old profile source bindings, queued work and cached content authority even when the plaintext key is unchanged. The app cannot infer vendor account identity from key possession or an operator label. It neither silently adopts legacy profiles nor automatically associates profiles with a replacement credential. A drained, separately implemented source-adoption/verification procedure is still required.

Key opening failures and configuration changes before authorization have no physical marker, paid-call budget or HTTP request. An error after a committed possible-call marker remains conservative and held. Unknown-work recovery does not reopen keys or call the provider. Saved Studio receipts retain original source/owner evidence and never resend; changed source authority prevents projection. Campaign audio received under replaced configuration is discarded under the existing superseded-result contract, with original generation metadata and no automatic replay.

These checks are process-local. A rolling deployment or changes in another process's environment are not a shared credential-revocation transaction. Fleet/config/cache drain is a prerequisite for cutover; already authorized/in-flight calls and Python/SDK copies need operational handling. No guaranteed plaintext zeroization or kernel isolation is claimed.

## Private configuration preparation

`python -m outreach.ops.voice_key_secret --generation <new-generation> --output <new-private-file>` reads a hidden terminal prompt. Explicit `--stdin` accepts bounded input when a hidden prompt is unavailable. The key is never an accepted CLI argument; parser failures also avoid echoing an accidentally supplied value. Input is bounded to 1,024 ASCII bytes, rejects mock/empty/envelope/control values, and never falls back to echoed terminal input.

The sealer requires `kms_v1` and pinned workload settings, captures policy across sealing, and writes a new exclusive mode-0600 file with fsync and inode-fenced partial cleanup. It reuses the previously tested OAuth sealer's private file writer. Existing/symlink targets are preserved. It installs no environment/configuration, touches no Mongo database, grants no provider work and performs no vendor request. Running it against actual KMS is a separate operator action; tests here use fake key services only.

Deployment configuration adds empty `OUTREACH_ELEVENLABS_API_KEY_ENC` and `OUTREACH_ELEVENLABS_KEY_GENERATION` settings. In scoped mode leave `ELEVENLABS_API_KEY` empty/mock, install the envelope with its exact generation through the private deployment mechanism, and keep provider/live flags disabled. The source changes, so current profiles remain unavailable pending explicit review. No production `.env`, key, envelope or AWS secret was changed during this slice.

Handler redaction now recognizes ElevenLabs header/configuration fields, including short header values and named logging mappings. Prepared key/configuration representations hide raw key/envelope storage; failure messages and CLI parser errors omit private provider/argument details. This does not prove remote vendor, SDK diagnostic, crash-dump or whole-product log retention.

## Verification and cutover

Eighteenth-slice verification: 1,424 backend checks pass in the final clean main run (1,404 outreach plus 20 account/auth companions), with 44 historical opt-in drills skipped. There are 61 new checks including eight actual Mongo cases; all 155 current focused consumer checks pass. The two new modules have 98% combined statement coverage (key custody99/private CLI98). Compile, medium/high Bandit, Compose/diff and final independent Python review pass. Frontend code is unchanged; the preceding slice's 93 tests/build remain historical evidence. No new Redis/Celery redelivery, physical SIGKILL, standalone-server, live-provider, AWS/IAM/egress/restore proof is claimed.

The new tests cover exact context integrity, downgrade/mixed-source rejection, key opening/rotation, ciphertext-free metadata, CLI bounds/hidden input/exclusive output, log redaction, production-adapter header use and final configuration checks. Eight actual replica-set cases use production snapshot/majority transactions, strict Studio indexes and production-default naive UTC BSON decoding. Concurrent workers make one request; all KMS opens/seals and adapter HTTP occur outside transaction callbacks. Unknown markers never decrypt/resend, and replacement source cannot receive an old result. Provider transport is mocked and all key services are local fakes.

Keep flags disabled. Drain API/media/beat/campaign/Studio/consent/profile/integration/transport/connection/suppression/erasure writers and caches before installing the compatible configuration/code. Verify replica-set transactions and strict indexes, inspect uncertain work, preserve original receipts/lease history, and complete explicit source review before any later separately authorized provider test. The sealer is not a deployment or migration command.

Remaining: other shared/provider/Webshare secrets, older campaign artifact custody, drained Studio held-outcome/received/source-adoption/vendor-verification tooling, integration transport/event boundaries, actual workload IAM/process isolation, kernel proxy-only egress, restore fencing, broader retention and separately authorized purchased IPRoyal/mailbox/voice pilot evidence. Manual verified-invoice provisioning remains; automated billing/proxy procurement is deferred.

Cleanup and delivery: owned temporary databases are absent; Mongo/storage were removed and ports 27028/6389 are closed. No Redis was started. All three repo/Desktop v2.19 specifications and their 77 relative report links/18 unique supporting reports match. Pre-edit backup: `/tmp/unravler-docs-before-v2-19`. Unrelated services/worktrees and prior dirty files were preserved. Local only: no commit, push, deployment, AWS/vendor call, purchase or production grant; legacy custody and disabled live/generation/Studio defaults remain.
