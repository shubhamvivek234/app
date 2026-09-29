# Unravler Outreach integrations: implementation and release plan

Status: design proposal, 2026-09-29. This document describes work to do; it is not a list of live integrations. Keep `OUTREACH_INTEGRATIONS_ENABLED=false` until the foundation and its security tests pass.

## 1. Decision and current state

Build one durable outreach event pipeline, then add customer webhooks and a small scoped API. Add Slack alerts, followed by a private Zapier/Make pilot using the released API and webhooks. Add HubSpot and Google Sheets after the event and identity rules are proven. Do not build separate event emitters for each provider.

What exists in this repository today:

| Area | Current state | Work still required |
| --- | --- | --- |
| Outreach webhook/API/Slack routes | Experimental code in `outreach/api/integrations.py`, gated off in `outreach/api/router.py` | Authorization, validation, rate limits, delivery, tests, and a release review |
| Webhook sender | `outreach/core/webhook_dispatcher.py` can sign and POST a test request | Durable events, delivery records, retries, safe network transport, and source-event wiring |
| Event sources | Campaign, lead, inbox, and email transitions exist in separate paths | Define verified event semantics and persist events with source transitions |
| In-app integrations UI | No production Outreach Integrations settings tab | Build only after its backing API is releasable |
| HubSpot, Google Sheets, Slack OAuth, Zapier, Make | No working customer connector | Separate provider implementations and external testing |
| Marketing page | `outreach-site/integrations.html` depicts these integrations as live | Correct claims before publishing the site; later add status by provider |

The scheduler already has `api/routes/user_webhooks.py`. Reuse audited transport/signature ideas where they fit, but keep outreach events, permissions, and customer data scoped to the outreach workspace. The current `utils/ssrf_guard.py` checks a URL's DNS answers before a request; it does not pin the HTTP connection to those answers, so it is insufficient by itself for user-controlled destinations.

## 2. Release principles

1. A provider event is emitted only after its source state is durably recorded. Celery/Redis is a delivery queue, not the sole event record.
2. External callbacks receive an event only for the workspace that owns the source. Every API read and write is scoped to that workspace and a permission or key scope.
3. Labels reflect evidence: an email provider's accepted response means **accepted for sending**, not delivered; connection acceptance and replies require a verified source. A sentiment label or `meeting_booked` is never inferred from reply text without an explicit reviewed classification.
4. Customer integrations cannot bypass paid seats, campaign warm-up, sender health, suppression, working hours, or sequence validation. Lead ingestion does not automatically launch a campaign.
5. Default event payloads contain IDs, event type, channel, confirmed status, and timestamps. Names, addresses, message bodies, and snippets require an explicit destination setting and documented retention/consent basis.
6. Provider tokens and webhook secrets remain encrypted at rest; API keys are shown once and stored only as a hash. Revocation and disconnect stop new work promptly.
7. Delivery is at least once. Consumers deduplicate with `event_id`; Unravler never promises exactly-once external side effects.

## 3. Event and delivery architecture

```text
Source transition (lead, campaign, inbox, email)
  -> MongoDB transaction: state change + unique outbox event
  -> outbox scanner claims event
  -> fan-out creates one delivery per subscribed destination
  -> integration worker sends with bounded retries
  -> delivery log / dead-letter review / replay control
```

For a source path where an Atlas transaction cannot be used, design an equivalent recoverable outbox write and prove with a crash/restart test that events cannot be silently lost. Never call a webhook or publish to Redis as the only record inside a FastAPI request or before the source update commits.

Use a versioned envelope and a stable event ID across retries:

```json
{
  "id": "evt_...",
  "type": "lead.replied",
  "version": 1,
  "occurred_at": "2026-09-29T10:14:22Z",
  "workspace_id": "ws_...",
  "data": {
    "lead_id": "lead_...",
    "campaign_id": "camp_...",
    "channel": "email",
    "source_status": "confirmed"
  }
}
```

Initial event catalog and source of truth:

| Event | Emit when | Do not emit when |
| --- | --- | --- |
| `lead.created` | Validated, deduplicated lead insert commits | Import validation fails |
| `lead.replied` | A LinkedIn or email reply is linked to the correct lead | Address/time match is ambiguous, or a send is merely accepted |
| `lead.connection_accepted` | Accepted connection is confirmed from the sender account | An invitation is sent or acceptance is inferred |
| `lead.stage_changed` | An explicit lead-stage update commits | A text classifier only suggests a stage |
| `campaign.paused` | Campaign status transitions to paused | Campaign completes normally |
| `email.accepted` | Gmail/Microsoft accepts an outbound message | Delivery or inbox receipt is unverified |

Do not ship event names that have no reliable producer. Define the payload schema and version per event; changing meaning or removing a field requires a new version. Include source IDs and aggregate revision in the outbox so duplicate worker attempts produce one logical event.

## 4. Persistence and worker contract

| Collection | Essential fields / indexes | Retention |
| --- | --- | --- |
| `outreach_event_outbox` | `id`, `workspace_id`, `dedupe_key`, `type`, `version`, `aggregate_id`, `occurred_at`, minimal `data`, `status`; unique `(workspace_id, dedupe_key)` | Only terminal events get an expiry date |
| `outreach_webhooks` | `id`, workspace, HTTPS URL, encrypted signing secret, validated event list, status, owner, timestamps; unique `(workspace_id, id)` | Until disconnected, then secret erased |
| `outreach_webhook_deliveries` | Unique `(event_id, destination_id)`, attempt count, `next_attempt_at`, claim lease, response code, sanitized error, terminal status | 90 days after terminal status, subject to policy |
| `outreach_api_keys` | Unique key hash, workspace, approved scopes, creator, prefix, expiry, `revoked_at`, last use | Retain metadata for audit; never retain plaintext key |
| `outreach_integrations` | Workspace/provider identity, encrypted OAuth grant, scopes, expiry, sync cursor, status | Erase usable grant on disconnect/seat expiry |
| `outreach_external_mappings` | Unique `(workspace_id, provider, external_account_id, object_type, internal_id)` plus external ID | Until disconnect/retention expiry |

One scanner claims outbox rows with a lease and creates deliveries idempotently. A separate worker claims each due delivery, increments attempts atomically, and records success only on a documented provider success response. Retry network failures, 429, and eligible 5xx with backoff and `Retry-After`; do not retry permanent 4xx. Start with five retries after the first attempt (for example 1m, 5m, 15m, 1h, 6h), then mark dead letter and show an admin review/replay control. Limit destination concurrency and queue depth per workspace. Do not auto-disable an endpoint solely because a 48-hour timer elapsed; use a stated failure threshold and alert its owner. Manual replay keeps the same event ID and creates an auditable new delivery attempt.

Add metrics for outbox lag, deliveries due, attempts, dead letters, rate limits, and provider failures. Alert on stuck leases and event lag. Test process restarts between source commit, fan-out, and external send.

## 5. Security and API contract

### Webhook destinations

- Require HTTPS, a public destination, no URL credentials, no redirects, bounded response size, and short connect/read timeouts. Re-resolve and validate on each attempt; pin the actual connection to a validated public IP or route through an egress policy that blocks private, metadata, and local networks. Cover IPv4/IPv6, DNS rebinding, redirects, and alternate numeric IP forms in tests. `is_safe_url()` alone is not sufficient.
- Sign the exact raw body with HMAC-SHA256. Include `X-Unravler-Event-Id`, `X-Unravler-Timestamp`, and `X-Unravler-Signature`; document the signature base string and a five-minute timestamp tolerance for consumers. Rotate signing secrets with a short overlap period. Keep the event ID stable across retries, but issue a fresh timestamp and signature for each delivery attempt so late retries remain verifiable.
- Show the signing secret only at creation/rotation. Redact destination tokens, reply text, request bodies, and response bodies from logs. Validate allowed event names and cap webhook count per workspace.
- Distinguish outbound customer webhooks from inbound provider webhooks. Inbound callbacks need each provider's own signature/state validation and are not covered by the outbound HMAC design.

### Public REST API

- Start with `unr_live_` keys backed by at least 32 random bytes, a hash, an approved scope allowlist, expiry/revocation, and a workspace-bound owner. Do not offer `unr_test_` until an isolated sandbox actually exists.
- Every endpoint checks the relevant key scope (`campaigns:read`, `leads:read`, or `leads:write`), current workspace entitlement, and resource ownership. Use a Redis-backed per-key/workspace rate limit with bounded response sizes and pagination. Return stable `429`/`Retry-After` behavior.
- `POST /api/v1/outreach/public/leads`: reuse the existing lead importer/validator, canonical URL and email validation, campaign-state rules, suppression checks, warm-up locks, deduplication, and seat limits. Require `Idempotency-Key` and return existing lead identity on a safe repeat. A write must never enroll into a campaign that the UI itself would reject.
- `POST /api/v1/outreach/public/leads/{id}/pause`: use the same lead-stop service as the UI. `GET /api/v1/outreach/public/campaigns` and `GET /api/v1/outreach/public/leads/{id}/history` return paginated, permission-filtered records only. Do not include raw session tokens, mailbox data, or unconfirmed provider outcomes.
- Do not expose campaign launch, resume, connection, or message-send APIs in this first release. Give keys names, creation time, last use, revocation, and one-time copy UX. Audit key creation, use, and revocation.

The existing experimental API presently accepts caller-chosen scopes without enforcement, has no rate limit or idempotency key, and inserts leads directly. Replace those paths before enabling `OUTREACH_INTEGRATIONS_ENABLED`; a feature flag is a release gate, not proof of readiness.

## 6. Provider rollout

| Order | Integration | First useful release | Later expansion / external dependency |
| --- | --- | --- | --- |
| 1 | Custom webhooks | Verified events, signed delivery, logs, retry/replay | Optional richer PII payloads after disclosure |
| 2 | Public API | Scoped keys, campaign reads, safe lead import/pause | More write methods only after abuse and entitlement tests |
| 3 | Slack | One destination channel via a user-created Incoming Webhook; verified alerts and a test message | OAuth install, multiple channels, digests. An Incoming Webhook is channel-specific; it is not a general bot token. [Slack docs](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks) |
| 4 | Zapier / Make | Private or invite-only integration using the released API and webhooks | Public listing after platform review and live partner tests; downstream apps require each customer's own Zapier/Make setup. [Zapier lifecycle](https://docs.zapier.com/platform/manage/version-lifecycle-states), [Make review](https://developers.make.com/custom-apps-documentation/app-review/request-app-review) |
| 5 | HubSpot | One-way, opt-in contact sync with explicit field mapping and stable object IDs | OAuth installation, token refresh, conflict policy, then optional inbound changes. Check current distribution limits and listing requirements before scaling: [HubSpot notice](https://developers.hubspot.com/changelog/new-marketplace-distribution-app-install-limits) |
| 6 | Google Sheets | User-selected spreadsheet, manual import with preview and deduplication | Scheduled import/status sync after cursor and conflict tests. Prefer file-limited `drive.file` where suitable; broader Sheets scopes can require verification: [Google scope guide](https://developers.google.com/workspace/sheets/api/scopes) |

Slack: validate the exact `hooks.slack.com` or approved GovSlack host and path for pasted webhook URLs. Store encrypted URL; test without echoing it. Default alerts should contain a lead link and verified event type, not a full private reply. A digest runs in the workspace's chosen time zone and records its aggregation window; booked-call counts require a real recorded booking signal. OAuth distribution and Marketplace listing have different requirements: [Slack distribution guide](https://docs.slack.dev/app-management/distribution/).

HubSpot: connect the specific portal through OAuth, request only fields and scopes used, and store a per-workspace portal/object mapping. Create/update contacts idempotently. Never overwrite a CRM field with an older Unravler value. Do not create deals based solely on an AI-positive reply; require an explicit user rule tied to a confirmed stage. Full two-way sync needs ownership, conflict, deletion, and loop-prevention rules before launch.

Google Sheets: reuse existing CSV import as the fallback. Ask users to select one spreadsheet; preview column mapping and formula-like values before import. Store spreadsheet and row identifiers so status updates do not overwrite arbitrary rows. Treat untrusted cell text as data, prevent formula injection in exports/writes, and handle revocation, quota, backfill, row deletion, and duplicate imports. Avoid broad Drive access.

Zapier/Make: expose only event triggers with a real producer and actions backed by released public API endpoints. Implement subscribe/unsubscribe for REST hooks, validate callback destinations, and clean up subscriptions. A listing does not make Unravler a native integration with every downstream product. Do not put “5,000+ connected tools” or “instant” on the public site until the app is published and the documented triggers are working.

## 7. Product UI and marketing

Add an Integrations area in Outreach Settings once the first connector is releasable. Show a provider's actual state: Available, Connected, Needs attention, or Planned. Webhooks need event selection, one-time secret reveal, signed test, delivery history, retry/replay, and disable/delete. API keys need explicit scopes, expiry, one-time reveal, last use, and revoke. Provider OAuth screens need their exact permissions and disconnect behavior.

Before publishing `outreach-site/integrations.html`, replace current claims of live Zapier, Make, HubSpot, Sheets, Slack, custom webhooks, and public API support with “planned” or “pilot” where appropriate. The site is a static future-domain artifact today; its live feature claims are ahead of the backend. Update public copy only when each end-to-end acceptance gate below passes.

## 8. Delivery slices and acceptance gates

The original four-week schedule assumes approvals and provider testing that are not under our control. Treat these as sequenced slices; estimate dates after the first real provider accounts and data contracts are available.

1. **Foundation:** Freeze versioned event definitions; implement transactional outbox, deduplicated fan-out, delivery leases/retries/dead letters, indexes, observability, and safe egress. Gate: duplicate/restart/DNS-rebind and cross-workspace tests pass; a recorded source transition yields one logical event and one delivery per subscription.
2. **Developer surface:** Replace the experimental webhook/API routes with scoped, rate-limited, idempotent services; add admin UI and docs. Gate: lead import/pause has the same validation as the UI, key scopes/revocation work, and a test endpoint can receive a verified signed event after a worker restart.
3. **Slack pilot:** One consented workspace and channel, confirmed event alerts, secret rotation/disconnect, no message body by default. Gate: real Slack delivery and failure recovery recorded end to end.
4. **Automation private pilot:** Zapier and Make private app versions with subscribe/unsubscribe, at least one trigger and one action each. Gate: one customer-owned workflow per platform passes duplicate, revocation, and retry tests; then submit public review if worthwhile.
5. **CRM and Sheets:** HubSpot one-way contact sync, then selected-file Google Sheets import, followed by optional outward status logging. Gate: real OAuth, token refresh/revocation, mapping conflicts, tenant isolation, and provider quotas tested with consented accounts.
6. **Public rollout:** Documentation, privacy/data retention, support/incident handling, pricing impact, provider listing approvals, and marketing claims reviewed. Gate: production flags enabled gradually for named workspaces, delivery metrics stable, and rollback verified.

Keep the LinkedIn live-action flag and email-send gates independent of integrations. An integration may deliver only events that the underlying feature actually produced. Product/legal review of session-based LinkedIn outreach remains a separate release gate; integration distribution does not authorize that activity.

## 9. Open product decisions

- Which verified events and minimal fields are useful to the first pilot customers? Decide before building a broad event catalog.
- Should API access be included in the $59 sender seat or offered as an add-on? Set quotas from measured usage, not a guessed 60 requests/minute.
- Which data may leave Unravler for a customer-controlled webhook, Slack, CRM, or spreadsheet, and for how long are delivery logs retained?
- Is the first customer demand for CRM sync strong enough to justify HubSpot before Zapier/Make? Reorder only after discovery, keeping the event/API foundation first.
- Who owns provider app registrations, OAuth verification, listing submissions, and support for revoked connections?
