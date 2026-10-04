# Paid outreach pilot: sender seats and dedicated IPs

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
