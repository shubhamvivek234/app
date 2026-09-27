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
