# Unravler.io — LinkedIn credential custody foundation
Version: 2.12.0 | Updated: 2026-10-03 | Status: Local implementation; AWS and deployment validation pending

The eleventh slice adds an opt-in, context-bound KMS/AES-GCM path for pending and installed LinkedIn cookies, exact workload-role checks and private drained migration. It does not activate outreach or establish per-container IAM isolation. The default remains `legacy_fernet` so existing installations do not silently break during an unverified cutover.

## Implemented scope

- Each nonempty `li_at`, JSESSIONID and optional `li_a` gets its own random 256-bit data key, 12-byte nonce and authenticated `uc1` envelope. The envelope identifies the exact KMS key ARN and format. Independently supplied workspace, sender, credential/job generation, purpose and environment must match before unwrapping.
- KMS context contains canonical framed scope/environment hashes, application, format and purpose. It contains no raw cookie or tenant identity. These hashes remain pseudonymous; encryption context is visible in AWS audit records.
- KMS mode accepts no plaintext, mock, legacy Fernet or cross-context fallback. Duplicate JSON keys, unknown fields, coerced versions, malformed encodings and tampered material deny access. Unmapped synchronous Voyager/Fernet callers reject scoped envelopes before transport.
- The key adapter permits only a configured EC2 role, ECS relative credential source or web identity. Static credentials, profile/process sources and endpoint overrides are excluded. Regional TLS endpoints, verified CA trust, IMDSv2-only fixed link-local metadata without proxy inheritance and the web-identity source STS client are pinned before credential resolution.
- STS and KMS use one frozen temporary credential pair per operation. Account, assumed-role name, unique IAM role ID and returned KMS key ARN are checked. This rejects a recreated role with the same name. The adapter has two concurrent slots per process, bounded SDK timeouts and one SDK attempt. Cancelled/timed-out threads retain their slots until they actually finish; prefork children reset inherited pool locks. SDK DEBUG logging is rejected at entry because decoded bodies/signing headers can expose keys/tokens. Do not enable SDK debug logging while requests are running.
- API pending storage, verification/finalization, sequence execution, inbox sync, manual Engage/reply, search import, legacy Engage worker helpers and conditional launch checks use the async scoped opener. No KMS calls occur in Mongo transaction callbacks. Pending secrets are rewrapped for the actual installed generation; a key-service delay cannot extend the original capture deadline.
- Pending insertion shares workspace erasure ordering and write fences on current paid access and connection lock. A lost insertion acknowledgement reads back the exact job and preserves its resources even if a worker has already claimed/finalized it. Unreadable/absent outcomes retain the original lock/slot/lease references with custody deadline and require operator review. A missing row is not proof of non-insertion. Ambiguous orphan locks are deliberately retained; this slice does not add an automatic orphan-release procedure.
- Existing secret fields are reused, so expiry/disconnect/erasure can scrub the envelopes. Legacy cookie/CSRF aliases now participate in credential fences, public sanitization and cleanup. Migration receipts are tenant-scoped metadata without ciphertext, cookie values or TTL, and are included in outreach erasure.

## Drained migration contract

`CredentialMigration` is private and exposes no customer endpoint. Inspection returns only scope, generation, blockers and a digest. Migration requires KMS mode, disabled live actions, an identified operator, an exact inspection digest and an explicit assertion that all credential writers/readers have been stopped and drained.

The sender must be paused, disconnected or require reauthentication. Its existing execution record must be idle, owner/token-free and latched stopped. Active/warming campaigns, uncertain/in-flight physical requests, connection locks/jobs or unfinished installation block migration. A snapshot/majority transaction first checks and writes existing authorities under the workspace guard; unsupported standalone MongoDB and erasure deny before key-service work. Scope/permission/material changes during sealing deny the final install.

Only strictly decryptable legacy Fernet cookie/CSRF values qualify. Historical plaintext CSRF/cookies and invalid ciphertext require reconnection or separate provenance review; no automatic adoption occurs. Migration preserves the credential generation and paused permission, requires new inbox coverage, removes legacy aliases and atomically records the replacement plus its receipt. Transaction retries reuse the newly sealed envelopes without another KMS call. A retry after a saved receipt does not reseal or resume; it reports whether the current material still matches that receipt.

## Configuration and operator procedure

Configuration is present in `docker-compose.yml`; `docker-compose.prod.yml` is its existing symlink. The shared environment mapping is configuration plumbing, not proof that containers have distinct role credentials.

| Setting | Default / requirement |
|---|---|
| `OUTREACH_CREDENTIAL_CUSTODY_MODE` | `legacy_fernet`; explicit `kms_v1` cutover only after validation |
| `OUTREACH_CUSTODY_ENVIRONMENT_ID` | Required, independently supplied environment identity in KMS mode |
| `OUTREACH_KMS_KEY_ARN` | Exact commercial-region single-Region UUID KMS key ARN; no aliases |
| `OUTREACH_KMS_ROLE_ARN` | Expected workload IAM role ARN in the same account |
| `OUTREACH_KMS_ROLE_ID` | Actual immutable role unique ID, not merely its name |
| `OUTREACH_KMS_REGION` | Exact key region |
| `OUTREACH_KMS_CREDENTIAL_PROVIDER` | `iam-role`, `container-role` or `assume-role-with-web-identity` |

1. Keep live, conditional launch, mailbox/finder and campaign voice-generation flags disabled. Stop and actually drain old API, scheduler, transport, inbox, connection, integration, media and erasure writers/readers. Stop each sender and its campaigns; resolve ambiguous physical/finalization work first. A CLI drain string is an operator assertion, not detected process quiescence.
2. Verify real snapshot/majority transactions and actual indexes. Snapshot/export the stopped state under the approved backup policy. Run migration from an isolated operator workload with the intended role, key, environment and existing Fernet key, never with static AWS credentials.
3. Separately validate the chosen credential source, role unique ID and STS identity, KMS key policy and grants. Restrict `kms:GenerateDataKey` and `kms:Decrypt` to the exact key and intended purpose/application/format/environment context; distinguish temporary migration permission from long-term service permission. IAM/KMS policy installation and real deny tests are not performed by this code.
4. Inspect and migrate each eligible sender using the trusted backend environment; no cookie/key value belongs in an argument:

```bash
python -m outreach.ops.pilot inspect-credential-custody --workspace WORKSPACE --sender SENDER
python -m outreach.ops.pilot migrate-credential-custody --workspace WORKSPACE --sender SENDER --operator OPERATOR --review-digest DIGEST --workers-drained I_PAUSED_AND_DRAINED_ALL_CREDENTIAL_WRITERS
```

5. Review the metadata receipt and `current_matches`; inspect replacement/blocked rows afresh. Migrate all eligible installed rows before starting KMS-mode consumers, or keep unmatched senders stopped for reconnection. Pending jobs use different purposes/generations and are not adopted by installed-session migration.
6. Recheck scope-swap/role/key/denial behavior with separately authorized AWS evidence, then resume only the required stopped runtime for offline validation. Do not grant execution or enable live actions as part of migration. Switching back to legacy mode cannot decrypt `uc1` envelopes. Key rotation and KMS-to-KMS migration require a separate reviewed procedure.

## Evidence

934 distinct outreach checks pass: 890 main-suite checks plus 5 broker/outbox, 35 physical provider and 4 voice crash cases. Twenty account/auth companions pass in the same 910-test main run (44 drill cases are skipped there and run separately). The slice adds 104 custody checks, including 16 real MongoDB cases; prior actual-Mongo coverage now totals 168 checks. The standalone negative case also verifies migration denial before KMS. Actual receipt indexes have no TTL.

The four custody modules have 96% combined statement coverage: envelope 97%, workload 97%, session 96%, migration 91%. Compilation, medium/high Bandit, whitespace and both Compose configuration checks pass; Compose reports existing unset environment warnings in the offline check. Independent Python review approves the bounded slice after the pending-insert acknowledgement fix. The main suite retains the multipart deprecation warning; the deliberate held-lock fork regression triggers Python's multithreaded-fork warning.

No UI behavior changed; the previous 86 frontend tests and production build remain the frontend baseline. They were not rerun for backend-only changes.

The new checks exercise real AES-GCM, mocked KMS/STS identity and source construction, bounded cancellation/timeout/fork behavior, scoped API/worker rewrap and expiry, actual Mongo transaction rollback/revision/erasure races, saved-receipt recovery, actual indexes and pending insertion acknowledgement loss. The existing 44 Redis/Celery/SIGKILL provider and voice drills pass over loopback with fake credentials. No real AWS, LinkedIn, proxy vendor, mailbox, finder or TTS call was made in this slice.

## Remaining release gates

Proxy passwords, mailbox tokens, finder keys, voice artifacts, webhooks and shared application secrets still use the existing Fernet path. Default legacy installed-session compatibility remains deliberately permissive and is a cutover blocker, not a scoped-custody guarantee. Broader per-purpose custody and automatic key rotation are unfinished.

The API still opens installed cookies to validate campaign launch. Media/general services still share current environment mappings and legacy credentials. Application role checks do not prove separate per-container workload identities, metadata isolation or kernel restrictions; actual IAM and deployment evidence remain required. SDK/KMS access is control-plane traffic and is not sent through a LinkedIn seat proxy.

Environment context makes copied cookies fail in a different configured environment. It is not a fresh restore execution epoch, external durable revocation authority or a completed disaster-recovery drill. A restore with the same environment identity can still open the old cookies. Broker authorization/restore fencing, default-deny IPv4/IPv6 proxy-only transport routing and purchased-seat/mailbox pilots remain separate.

There is no DEK cache, and mutable local key copies are scrubbed. Python, SDK and crypto libraries can make immutable copies; this is not guaranteed memory zeroization. A timed-out SDK thread cannot be forcibly terminated. Cached plaintext session objects still require actual process drain. Sanitized application errors do not justify transport/body logging.

Owned test MongoDB and Redis were stopped after verification; ports 27028/6389 are closed and no temporary test databases remained. The three v2.12 specifications and this report match their Desktop copies; relative release links resolve.

Local changes only: no commit, push, deployment, production IAM/key changes, provider purchases, execution grants or live-flag changes. Backup: `/tmp/unravler-docs-before-v2-12`.

## Sources and prior evidence

AWS describes data-key responses and context-bound decryption in [GenerateDataKey](https://docs.aws.amazon.com/kms/latest/APIReference/API_GenerateDataKey.html) and [Decrypt](https://docs.aws.amazon.com/kms/latest/APIReference/API_Decrypt.html). Credential-provider behavior is documented in [Boto3 credentials](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html); the application narrows that normal chain rather than accepting all SDK providers.

Prior slice: [Offline voice preparation](UNRAVLER_IO_OFFLINE_VOICE_PREPARATION_RELEASE.md). Installation/repair: [Operator repair and pending custody](UNRAVLER_IO_OPERATOR_REPAIR_AND_CUSTODY_RELEASE.md). Closure/retention: [Erasure and retention](UNRAVLER_IO_ERASURE_AND_RETENTION_RELEASE.md). Physical ordering: [Suppression ordering](UNRAVLER_IO_SUPPRESSION_ORDERING_RELEASE.md), [Atomic dispatch authority](UNRAVLER_IO_ATOMIC_DISPATCH_AUTHORITY_RELEASE.md).
