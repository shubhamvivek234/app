# Unravler.io — managed proxy custody and orphan connection-storage repair
Version: 2.13.0 | Updated: 2026-10-03 | Status: Local implementation; deployment and AWS validation pending

The twelfth slice extends opt-in custody to managed IPRoyal passwords and adds a private stop-only repair for proven pre-installation connection-storage orphans. Default custody remains `legacy_fernet`. Live actions and campaign voice generation retain disabled defaults. No commit, push, deployment, real key-service/provider call, production grant or provider purchase was made.

## Implemented scope

- Managed imports retain a credential generation and custody workspace. In KMS mode, a password receives its own random data key/AES-GCM envelope, with independently supplied workspace, canonical asset identity, generation, transport metadata, `proxy_password` purpose and environment. Public static IPv4 and typed/bounded transport fields are required. Changing provider, host, port, username, country, asset or generation prevents opening.
- Proxy password cryptography is asset-bound. Sender ownership is enforced separately by the existing one-sender lease, slot, paid term and final dispatch authorization. It is not cryptographically bound to a sender at initial import, because the asset has not yet been assigned.
- New imports and private migration reuse the prior pinned temporary-role, exact role-ID/key-ARN, bounded SDK and no-fallback key adapter. Import verifies transaction/workspace capability before sealing and checks erasure again at insertion. Reservation rejects incompatible workspace/custody inventory without silently substituting a provider or country.
- Sequence, manual Engage/reply, inbox, search, verification and conditional launch prepare each proxy asynchronously before transport. The actual URL and its encrypted-material digest use the same captured record across key-service awaits. The prepared object excludes the URL from its representation and is operation-local; no global password cache is introduced. This does not establish Python memory zeroization or kernel proxy-only routing.
- Final authorization remains database-only. It compares the captured URL and exact encrypted asset/transport/generation against the sender copy and current inventory, with existing-row write fences and the workspace guard. Key-service delays cannot extend existing deadlines or permissions. No KMS calls occur inside transaction retries.
- Private drained migration accepts only a strictly decryptable legacy managed IPRoyal asset with verified workspace ownership, valid provider term and exact stopped sender aliases. Ambiguous/multiple sender bindings, leases without a proven account, unfinished connection/physical/campaign/execution rows and alias divergence deny migration. Unassigned proven assets may migrate. Inventory and both stored `proxy`/`proxy_config` aliases change atomically with a metadata receipt; cookie generation, stopped permission, leases and provider terms are preserved. A saved receipt retry performs no resealing or transport and reports whether current material still matches.
- Connection locks capture protocol-one reference-only storage proof in a separate guard transaction before attempting pending insertion: base account digest, asset, country and job-owned reservation flags. Final insertion rechecks current account/lock and absence of a saved job/closure. Lost acknowledgement after an attempted insert still retains lock/slot/lease and reads the exact durable job. An unreadable readback cannot fabricate failure or release resources.
- Stop-only storage repair requires disabled live actions, an identified operator, evidence, exact fresh inspection and explicit drain of **all credential/connection writers**, including API and recovery/publisher processes. An absent job alone is insufficient: the protocol/base account and resource owners must match, with no pending-job physical evidence, active sender ownership or installation fence. Older ambiguous locks and records with a now-present job remain held.
- The repair transaction latches permission and pauses the exact current sender/campaigns, saves a reference-only `storage_stopped` closure, then removes only this job's unused reservations and lock. Reconnect credentials/generation and reused IP leases/slots remain intact. The closure deliberately omits TTL-indexed `created_at`, while the workspace/id unique index prevents delayed insertion from recreating it. A retry returns the saved closure without touching replacement tokens/resources. Transaction failures roll back stop, closure and cleanup together.
- Installed-generation permission grants remain blocked while a protocol-one storage lock or unknown storage outcome is unresolved, even with explicit unlatching. Pending verification remains job-bound and deadline-capped. The sender connection dialog terminates polling for stopped/repaired/cancelled jobs and does not report them as connected.
- Proxy migration receipts participate in existing tenant erasure. Ordinary storage closure metadata can be removed only after permanent workspace exclusion governs all participating late writers. Minimal provider-term evidence and ownership remain under the existing retention contract. This is not backup/remote-vendor erasure or a legal retention decision.

## Private operator procedure

Keep live actions disabled. Stop and drain old/new API, connection verification/install/cleanup/publisher, LinkedIn transport, inbox, integration, media and other credential writers before either procedure. A CLI acknowledgement is an operator assertion, not proof that running processes or cached secrets have stopped. Verify replica-set transactions and actual indexes first; standalone Mongo denies before KMS or resource cleanup.

For proxy migration, configure the same verified KMS workload contract as [the LinkedIn custody foundation](UNRAVLER_IO_CREDENTIAL_CUSTODY_RELEASE.md) in the isolated operator process. Setting `kms_v1` on live services before compatible cookies **and** proxy inventory/sender copies have migrated causes denial. Webshare provisioning and the other provider/shared-secret families are not covered by this slice. Keep stopped permission and paused campaigns through migration; inspect and authorize any future pilot separately.

```bash
.venv/bin/python -m outreach.ops.pilot inspect-proxy-custody \
  --workspace WORKSPACE --proxy ASSET_ID
.venv/bin/python -m outreach.ops.pilot migrate-proxy-custody \
  --workspace WORKSPACE --proxy ASSET_ID --operator OPERATOR \
  --review-digest INSPECTION_DIGEST \
  --workers-drained I_PAUSED_AND_DRAINED_ALL_CREDENTIAL_WRITERS
```

Storage repair uses the job reference in the sanitized storage error. Inspect the exact retained lock and resources after draining all writers. If a job is now present, use its existing recovery/review workflow; if protocol/base ownership or verification/installation evidence is ambiguous, retain the records for separate provenance review. This command cannot install/restore credentials, resend verification, release connected provider assets or grant permission.

```bash
.venv/bin/python -m outreach.ops.pilot inspect-connection-storage \
  --workspace WORKSPACE --job JOB_ID
.venv/bin/python -m outreach.ops.pilot stop-connection-storage \
  --workspace WORKSPACE --job JOB_ID --operator OPERATOR \
  --review-digest INSPECTION_DIGEST --evidence 'Specific drained inspection evidence' \
  --workers-drained I_PAUSED_AND_DRAINED_ALL_CREDENTIAL_WRITERS
```

Commands print identifiers, digests, blockers and metadata receipts, never proxy passwords, cookie bytes or ciphertext. Avoid putting secrets in operator evidence. Repeat a completed operation using its original review digest; a replacement account/asset is never silently adopted. Provider renewal, purchase, cancellation and automated billing remain outside scope.

## Verification

The 89 new backend checks pass, including 28 actual MongoDB cases over a disposable replica set and a real standalone denial. They cover context/transport swaps, mutation during key opening, warm-up wiring, import/reservation scope, exact alias migration, physical authorization without key-service calls, existing-row races, projection rollback, lost acknowledgements, reference closure uniqueness and erasure. Key services and credentials are local fakes; no AWS/STS/KMS/provider calls occurred.

The three new custody/repair modules have 93% combined statement coverage: proxy custody 97%, proxy migration 91% and storage repair 92%. All 999 main checks pass (979 outreach plus 20 account/auth companions); 44 drills skipped there pass separately (5 broker/outbox, 35 physical provider and 4 voice crash cases), for 1,023 distinct outreach checks and 1,043 total backend checks. All 88 frontend tests and production build pass. Compilation, medium/high Bandit, whitespace and Compose configuration pass. Independent Python review approves the bounded local slice. Existing multipart/fork deprecations and frontend dependency/Tailwind/source-map warnings remain; none is a new test/build failure. The first broad run exposed three outdated mock fixtures, corrected without relaxing production guards. Owned local services were stopped after final verification, with no temporary databases or listening drill ports remaining.

## Remaining release gates

Broaden mailbox/finder/voice/shared-secret custody and the Webshare lifecycle separately. Verify deployed IAM role trust/key policies and actual per-workload identity, process/kernel proxy-only egress, restore epoch fencing, and separately authorized purchased IPRoyal sender/mailbox checks. Do not infer production isolation from mocked role checks or encrypted credentials. Drain older/raw writers and cached credentials, verify indexes/transactions, and keep flags disabled until those deployment and pilot gates are satisfied.
