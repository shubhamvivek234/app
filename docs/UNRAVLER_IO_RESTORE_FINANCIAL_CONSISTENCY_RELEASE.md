# Unravler.io v2.43 — stopped financial consistency and physical evidence review

Date: 2026-10-09. Local only, uncommitted and undeployed.

## Verified scope

The existing private restore inventory now compares each selected entitlement with its original selected invoice receipt: invoice identity, integer pilot seats, native UTC-millisecond paid-through term and manual_verified_invoice source must match. It reports missing/mismatched receipts, malformed/unproven payment metadata, stopped/revoked entitlements and expired terms. Entitlement payment_source is newly projected and bound into the private inspection digest. These are local metadata consistency checks, not authenticated payment or authorization; even a matching receipt plus matching global invoice guard cannot activate anything.

Selected outreach_physical_requests now yield explicit findings for preparing, in_flight/unknown_outcome, response_received and unknown/missing status. A received response still needs review; it is not established delivery or a repaired outcome. Known not_submitted rows and read_failed rows with mutation exactly false add no uncertainty finding, but supply no general completeness or retry authorization. No request is resolved, retried, refunded, deleted or relabelled. Original owners, receipts and evidence remain unchanged. Other provider-operation collections and uncertainty domains are not covered.

The v2.42 contract remains: matching prepared stopped epoch, five flags off and asserted all-writer/cache drain; one guard/snapshot/majority session for seven collections/global bindings,100 rows each and65,536 reviewed metadata bytes checked after reads. Existing guard/root/journal fence counters may advance; domain evidence remains intact. Limits do not establish network/memory bounds, source completeness, provider ownership or fleet/cache enforcement. Private aggregate output excludes raw invoice/IP/credential/owner/receipt material; metadata digests remain linkable and are not safe public identifiers. Empty and matching results always retain false activation_allowed/completeness_verified/provider_ownership_verified. No new CLI command, journal, schema or index; earlier v2.42 digests may change when payment_source becomes part of the reviewed projection.

## Verification

57 focused checks pass in12.30s:44 unit/CLI and13 real Mongo cases, including24 added cases (20unit/four native). Added native cases use the default naive-BSON codec and retained original unknown request, verify match/mismatch/missing/revoked payment relationships, report physical states and preserve exact entitlement/owner/receipt documents. Changes to current seats change the snapshot digest. The initial test expected two unknown physical rows but the shared fixture already retained a third; the expectation was corrected with no shared-fixture or runtime weakening. Initial checks were written before implementation (14red,26existing pass). Independent review identified contradictory read_failed mutation metadata; this now reports physical_state_unproven, with four added malformed-kind regressions.

Coverage is98% combined (core98%,CLI97%); compile/scoped Bandit/whitespace checks pass. Final restore regression:538 passed,2 opt-in physical-backup drills skipped,one existing warning in100.36s; no fresh full-backend or physical-drill claim. Independent Python review: Approved after correcting inconsistent failed-read metadata; independent44 unit/CLI checks pass.

Frontend/configuration/indexes and all unrelated earlier changes are preserved. No fresh full-backend, frontend or physical-backup claim is made. All work stays local: no commit,push,deployment,production source/config/flags/grants,real credential opening,AWS/provider call or purchase.

## Next boundaries

Remaining provider/resource and financial source reconciliation/completeness, unproven reply evidence and explicit new-epoch activation design/drills are still required. A negative inventory does not recover missing outside-backup facts or authorize grants. Actual deployment/IAM/kernel egress and pilot checks remain separate.

Owned replica PID98818/manifests/private storage removed after confirming only admin/config/local databases remained; no temporary databases,27028/27029/6389 closed,no Redis,user Mongo1735 preserved. All28 unchanged earlier source/test/cache fingerprints match; only the intended core and two test files changed among31 tracked fingerprints. Three specs/runbook/report and Desktop copies match149links/42reports; eight protected pre-edit copies remain at /tmp/unravler-docs-before-v2-43-20261009. Session memory is updated last.
