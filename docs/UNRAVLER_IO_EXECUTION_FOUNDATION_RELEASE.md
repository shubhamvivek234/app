# Unravler.io execution foundation — local release

Date: 2026-10-02. Based on the review of local commit `2187946`.
Status: implemented locally and reviewed with live actions disabled; not committed, pushed, or deployed by this task.

## Delivered

- Six compatible lifecycle contracts wrap the existing pilot authorities. There is no `SeatStatus` replacement migration. Subscription/procurement automation remains future work.
- Campaign changes revoke earlier authorization revisions. Pause reasons remain independent. Activation claims ownership before preparing leads and fences stale launchers.
- Sequence saves insert immutable snapshots and publish a conditional campaign pointer. The legacy sequence collection is a compatibility projection; a failed projection cannot lose the saved version. New imports persist enrollment identity; legacy operations keep their deterministic mapping.
- Reconnection changes credential generation. Inbox completion is published only after parsed, uncapped coverage and durable suppression processing. Freshness ages from scan start. Missing, partial, future, or old-generation coverage defers follow-ups and requests priority sync.
- A sender/recipient reply flag is monotonic. Thread content uses a revision check. Same-sender enrollments and subsequent imports consult the reply authority. Thread attribution remains separate from suppressing other enrollments.
- Sequence actions persist a logical intent and an embedded physical attempt. An expiring preparation claim can be replaced; an interrupted possible submission becomes unknown and never automatically sendable.
- Sequence sender ownership serializes different actions. In-flight ownership remains latched after a crash; this is not yet a lock shared by all sender traffic.
- Final dispatch checks run after preparation and evidence writes. A conditional lead write orders suppression recorded on the lead before calling transport. Conditional completion and scheduler writes preserve newer replies and manual pauses.
- Local recovery repairs the legacy reporting ledger from saved acceptance, or makes interrupted actions visible for review. Human decisions remain assertions, preserve original attempt evidence, and do not restart campaigns. Stale recovery cannot affect a later authorization revision.
- Mailbox readiness rejects future timestamps; incremental sync freshness now uses the beginning of the covered cycle. Existing bounded mailbox cursor and provider-send guards remain in place.

## Evidence

- 418 outreach backend tests pass, including the new execution tests and the 6 opt-in real local MongoDB tests.
- 6 real local MongoDB concurrency/fault tests use isolated random databases and fake provider transport. They verify duplicate intent publication/claims, sender ownership, stale-owner fencing, submission quarantine, saved-evidence repair, and concurrent sequence publication.
- 93% statement coverage across the seven new execution service modules; each is above 80%.
- 75 outreach frontend tests pass. Frontend production build passes with existing dependency, Tailwind, source-map, and bundle-size warnings.
- Python compilation, medium/high-severity Bandit scan, and whitespace checks pass.
- Python/security/concurrency review approves the bounded release with live actions disabled.

These results do not establish real LinkedIn delivery, complete live parser coverage, proxy route identity, or broker restart behavior. Final checks across campaign, entitlement, sender, DNC, and recipient documents are not one transaction. Only the lead suppression/ownership transitions have the tested single-document atomic boundary; strict authorization ordering across all authorities must be verified before live release.

## Cutover requirements

1. Keep provider-send/crawl flags disabled. Pause and drain old dispatchers and API-triggered provider work before changing execution authority. Retained broker jobs contain references; they are not execution permission.
2. Verify the existing unique `outreach_tasks(workspace_id, id)` index and the new intent/sequence/recovery indexes. Index creation errors must be resolved before rollout.
3. Preserve all legacy completed, accepted, uncertain, resolving, and stopped action records. Do not delete an intent/attempt or increment its identity to bypass uncertainty.
4. Active legacy campaigns missing authorization metadata fail closed. Review and explicitly pause/launch them; do not bulk grant revisions as a background migration. Launch binds nullable legacy lead metadata and initializes missing root nodes, including already-assigned leads.
5. Reconnects invalidate freshness. Obtain a complete, same-generation sync before follow-ups. A capped or unrecognized provider response is a blocker, not evidence of freshness.
6. For interrupted submissions, pause/drain the affected worker before human resolution. Review the provider evidence, then confirm the recorded action or stop the lead. A known non-submission can defer safely; a possibly submitted action requires review. Resolution retains the original attempt and never automatically resumes the campaign.
7. If rolling back, keep dispatch disabled and retain all new and legacy evidence. An older worker does not understand the new authorization protocol; restoring it is not a safe live rollback.

## Next implementation slice

1. Extend one common physical-request envelope and sender coordination across sync, search, sequence actions, manual inbox replies, Engage, and withdrawal. Replace process-local budget fallback and long crawler countdowns with fail-closed shared authority and durable due times.
2. Add expiring positive execution permission, operator latching, and the agreed content-approval policy. Validate every physical subrequest and stage-specific voice/email uncertainty before releasing those paths.
3. Add a separate intent publisher and real broker/process-crash fault tests. Preserve the Mongo authority and legacy operation boundary throughout cutover.
4. Implement and exercise the retained credential-custody, egress, and restore-epoch requirements. Verify purchased IPRoyal assets and the mailbox pilot independently before a separate live-action release decision.

Automated Stripe billing and provider procurement follow later. Existing manual verified-invoice provisioning remains the pilot contract.
