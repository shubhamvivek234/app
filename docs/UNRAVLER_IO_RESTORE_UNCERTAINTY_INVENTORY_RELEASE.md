# Unravler.io v2.50 — consolidated stopped uncertainty inventory

Date: 2026-10-10. Local, uncommitted and undeployed.

## Scope and behavior

The private restore inventory now covers intact restored rows in nine additional collections: mailbox connection jobs, OAuth browser states, mailboxes, mailbox sync jobs and reads, campaign voice preparation jobs, Voice Studio jobs, voice vendor metadata reads, and webhook/HubSpot deliveries. This consolidates the remaining selected OAuth, mailbox, voice and integration inspection into one change. It does not alter those workers or their dispatch/repair protocols.

Persisted job states produce pending, preparation, unresolved, recorded-result or stopped review findings. Missing, malformed and unrecognized required states produce state_unproven. Categories are review labels, not verified outcomes or permissions. For example, an OAuth job with status review_stopped and exchange_state unknown still reports oauth_exchange_unresolved; a disconnected mailbox with refresh_state possible/unknown still reports mailbox_refresh_unresolved. OAuth running/review_required jobs are conservatively unresolved even without a usable exchange substate. Interrupted mailbox/vendor reads remain unresolved despite being GET operations.

Substates are independent of parent job status. Studio review.outcome_at_review unknown remains unresolved after review_stopped. Campaign voice generation_result received/received_discarded reports recorded-result review even after superseded. Unmarked refresh state reports unmarked_review; explicit null/malformed state is unproven. OAuth browser-state presence reports review without interpreting expiry, opening PKCE material or treating it as evidence of submission. Optional absent voice outcome fields add no extra finding; their parent states still require review. Stopped/not_submitted/not_called labels never authenticate a non-call, provider revocation, refund, reclaim or replay permission. Terminal/received/installed/released labels never authenticate receipts, delivery, billing, artifact validity or provider ownership.

The new pure metadata classifier receives only sanitized flattened projections. Added collections project _id and required status/substate fields; browser states project only _id. Tokens, codes, PKCE, owners, consent/audio/input/output, messages, URLs, payloads, raw receipts, review evidence and budget rows are excluded. The new metadata contributes to the existing private linkable snapshot digest; the expanded projection changes prior digests. Output contains aggregate counts/findings and that digest, not raw operation identities or private material.

Twenty collections now share the existing bounds: 100 rows per collection and 65,536 serialized reviewed metadata bytes across the complete view. These checks occur after the projected reads and are not wire or memory limits. Capacity excess denies the entire report. Workspace-filtered queries share the existing snapshot/majority transaction and session, matching prepared stopped epoch, five disabled flags, asserted all-writer/cache drain, and synchronous late policy checks. Existing guard/root/journal fence counters can advance; this is not a claim of a mutation-free database call. No domain row, owner, receipt, history, hold, credential, resource, lease, reservation or budget is changed.

activation_allowed, completeness_verified and provider_ownership_verified remain false, including empty and apparently consistent inventories. Outside-backup financial/provider/source review remains required. There is no repair, uncertainty resolution, worker publication, credential opening, HTTP, refund, new schema/index/journal, apply command, grant or activation.

## Verification

Focused verification: 265 checks pass (196 unit/CLI and 69 actual Mongo checks) in 41.57s. The 91 added checks comprise 71 unit and 20 native cases. The initial 71 new unit cases failed before implementation. Combined statement coverage is 99% (inventory 99%, uncertainty classifier 100%, CLI 97%).

Native checks cover all seven job/read/delivery status families, all nine new collection limits, foreign workspace exclusion, private-field exclusion from the digest, retained original operation/physical/budget rows, refresh/browser and voice substates, a combined metadata-size denial, and one shared-session snapshot with later inserts into all nine collections. The earlier 49 native inventory checks also pass, including stopped-policy and standalone denial. No new production-index claim is made.

Independent Python review approves with no remaining material findings: 196 independently executed unit/CLI checks pass, and the 20 new native contracts were inspected without service actions. Compile, scoped Bandit and whitespace checks pass.

Final restore regression: 746 passed, two opt-in physical-backup drills skipped, and one existing multipart deprecation warning in 131.42s.

No fresh full-backend, frontend, physical-backup rehearsal, production index cutover or live-provider verification is claimed. Existing opt-in physical backup drills remain separate.

## Boundaries and next work

This is a bounded inventory of the selected intact workspace-scoped collections, not a complete uncertainty census. Erasure archives/holds, missing/deleted/provider-only records, LinkedIn connection finalization, manual-stage and sequence intent/attempt relationships are not added here. It does not authenticate underlying receipts, join all physical evidence, verify relationships/contradictory history, establish source completeness, prove drain, or establish participant serialization for writers outside the existing guard protocol. The new snapshot drill proves concurrent later inserts stay outside a single snapshot; it does not prove completeness or serialization of those writers.

Next: define and implement authenticated outside-backup reconciliation and completeness manifests for financial/provider/resource facts and unproven replies; then design explicit new-epoch activation and operational drills. Remaining credential/legacy cutovers, explicit integration activation, live budgeted health/cohort observations, combined verification and real deployment/IAM/kernel-egress/pilot evidence remain separate. Keep original uncertainty and stopped authority until those boundaries are satisfied.

All work stays local: no commit, push, deploy, production source/config/flags/grants, real credential opening, AWS/provider calls or purchases. Frontend unchanged.

Disposable Mongo PID 19293 was identified by exact command and matching owner manifests, then stopped; its owned storage/manifests were removed after confirming zero temporary databases. Ports 27028/27029/6389 are closed, no Redis was started, and the original user Mongo PID 1735 was preserved. All 44 final source/artifact fingerprints match; 39 earlier source/artifact fingerprints are unchanged. The eight pre-edit architecture/runbook copies remain private (directory 0700, files 0600) at /tmp/unravler-docs-before-v2-50-20261010. Repository/Desktop specifications, runbook and release report were synchronized; session memory is updated last.
