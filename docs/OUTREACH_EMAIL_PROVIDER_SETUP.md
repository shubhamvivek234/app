# Outreach email provider setup (gated pilot)

Outreach email uses a customer's own Gmail or Microsoft mailbox. It does **not**
reuse Unravler's transactional sender, the scheduler's social OAuth grants, or a
mailbox password. One mailbox is associated with one paid outreach sender seat.
The code and tests are not a substitute for Google/Microsoft approval or a
consented live mailbox test.

## Provider applications

Register separate OAuth applications and configure these exact callback URLs
on the public app host (replace the host with the deployed frontend domain):

- Gmail: `https://APP_HOST/api/v1/outreach/mailboxes/gmail/callback`
- Microsoft: `https://APP_HOST/api/v1/outreach/mailboxes/microsoft/callback`

The actual OAuth redirect URLs must use the **same public origin as the
frontend**, not the separate API host. In the current Vercel deployment,
`/api/v1/outreach/mailboxes/*` is a first-party reverse proxy to the API, so
register `https://APP_HOST/api/v1/outreach/mailboxes/.../callback` instead of
`https://api.unravler.com/...`. This is required for the short-lived, HttpOnly
browser-binding cookie; cross-site XHR cannot reliably set a SameSite=Lax
cookie. Verify the rewrite preserves `Set-Cookie` and callback cookies in a
real browser before enabling connections. If hosting changes, provide an
equivalent same-origin proxy.

The Gmail application requests `openid`, `email`, `gmail.send`, and
`gmail.readonly`. The Microsoft application requests delegated `openid`,
`offline_access`, `User.Read`, `Mail.Send`, and `Mail.Read`. Gmail mailbox read
access is a restricted scope; public rollout requires Google's applicable
OAuth verification and security review. Microsoft organizational tenants may
require administrator consent. Request only the scopes actually implemented
and disclosed in the privacy policy.

Normal reply synchronization reads message headers. For suspected delivery
failure notices, the worker requests the bounded raw MIME content to parse
structured delivery-status fields. The provider grants mailbox-read access,
which is broader than header-only access; public disclosures must say so.

Set the corresponding `OUTREACH_GMAIL_*` or `OUTREACH_MICROSOFT_*` client ID,
client secret, and redirect URI in the server environment. Set
`OUTREACH_MICROSOFT_TENANT=common` for work/school and personal accounts, or a
validated tenant ID for a single tenant. The existing `ENCRYPTION_KEY` must be
configured; never put provider secrets in frontend variables or Git.

## Release controls

The production Compose file passes four independent flags to the API, worker,
and Beat processes. All default to `false`:

| Flag | Purpose |
| --- | --- |
| `OUTREACH_MAILBOX_CONNECTION_ENABLED` | Allow a paid sender to initiate mailbox OAuth. |
| `OUTREACH_EMAIL_SYNC_ENABLED` | Enable reply/bounce synchronization. |
| `OUTREACH_EMAIL_SEND_ENABLED` | Permit one-to-one sequence sending only when sync is healthy. |
| `OUTREACH_HUNTER_ENABLED` | Allow the workspace's own encrypted Hunter key to find addresses. |

Do not enable automated email sends merely because OAuth connects. Confirm a
fresh reply sync, opt-out suppression, paid-seat enforcement, and provider
acceptance-versus-delivery reporting first. The separate LinkedIn live-action
flag remains off until its own product/legal decision and live pilot.

If a provider request times out after dispatch, the campaign pauses and the
step is never resent automatically. A workspace admin must inspect the provider
Sent folder, use Settings → Action reviews to record an evidenced sent/not-sent
decision, then separately review and resume the campaign. A definite provider
rejection stops only that lead. The experimental public API, Slack, and custom
webhook router is outside this pilot and defaults off under
`OUTREACH_INTEGRATIONS_ENABLED=false`; do not enable it for customers without
separate security and end-to-end event-delivery verification.

## Required live pilot before customer rollout

1. Connect one internal Gmail and one internal Microsoft test mailbox; verify
   one-time OAuth state, token refresh, disconnect, and expired-seat cleanup.
2. Send only to consented internal recipients. Verify provider-accepted status
   is **not** displayed as delivered.
3. Reply, opt out, and produce a test non-delivery report. Confirm the correct
   lead is stopped before another sequence step, without matching an older or
   unrelated conversation.
4. Revoke provider consent, let reply sync become stale, pause a campaign, and
   expire the paid term. All subsequent sends must fail closed without a
   provider request.
5. Review workspace isolation, token encryption, audit retention, rate limits,
   provider terms, and applicable email-marketing law with product/legal owners.

Google and Microsoft app approvals, customer tenant consent, and provider
test accounts are external prerequisites. Do not claim public readiness from
mocked API tests alone.
