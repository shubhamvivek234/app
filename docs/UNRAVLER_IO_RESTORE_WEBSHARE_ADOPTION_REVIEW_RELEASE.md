# Unravler.io v2.46 — stopped Webshare adoption metadata review

Date: 2026-10-09. Local, uncommitted and undeployed.

## Scope

The private restore inventory now compares selected Webshare adoption markers with retained adoption receipts. The resource requires exact workspace/noncontradictory sticky scope,a valid bounded resource reference,hex adoption ID/source digest and a valid retained root basis (current import basis only when the root field is absent). Exactly one selected receipt for that resource must match adoption ID,completed status,source digest and adopted basis. Missing,malformed,foreign,changed or ambiguous records report webshare_adoption_review_required; agreement reports local_webshare_adoption_matches. A present null/malformed root cannot fall back to current import basis.

The comparison concerns retained metadata only. It does not reconstruct or authenticate original source facts, prove journal provenance, adopt a resource, validate complete provider/import/adoption/lifecycle history, prove credentials or provider ownership, or authorize use. Original imports without adoption markers/receipts conservatively require review here; their operational validity is not changed. Adoption and lifecycle findings are independent; matching one does not satisfy the other. Orphan receipts are counted/digest-bound, not individually reconciled. Source completeness remains false even for empty/matching results.

New inventory projections bind proxy_adoption_id/proxy_adoption_source_digest. The ninth collection,outreach_proxy_adoptions,projects only receipt/resource identity,status,source and adopted-basis digests. Same workspace-filtered guard/snapshot/majority session,100 rows per collection and65,536 reviewed metadata bytes across the entire report remain; after-read limits are not network/memory bounds. Expanded scope can change prior inventory digests. Matching prepared stopped epoch,five flags off,asserted writer/cache drain and late policy checks remain mandatory. Existing guard/root/journal fence counters may advance; no domain receipt,resource,lease,credential,reservation,financial state,held owner/token or physical evidence is changed.

No ciphertext or original secret is opened. Unrelated private receipt fields stay outside projections/digests; output remains aggregate private metadata findings with linkable digest,without raw source/resource/receipt/credential material. Every result keeps activation_allowed/completeness_verified/provider_ownership_verified false and requires external financial/resource/source review. No new schema,index,journal,apply command,grant,activation,replay,refund or provider action.

## Verification

108 focused checks pass(78 unit/CLI+30 native Mongo)in24.11s,16 new cases(11unit+5native);99%combined coverage(core99%,CLI97%). Added unit cases cover matching/missing markers,missing/foreignscope/status/source/basis/review-ID conflicts,duplicates,absent-root fallback and present-null root denial. Five native cases cover matching/missing/foreign receipt/changed basis/capacity,exact resource/receipt/physical-evidence preservation and excluded private fields. Initial nine red cases preceded implementation. Independent Python review approves;78 independent unit/CLI cases pass and scoped Bandit is clean. Its two recommended null-root/receipt-ID regressions were added and pass in the final focused run. Compile/scoped Bandit/whitespace pass. Restore suite:587 passed,2 opt-in physical-backup drills skipped,one existing warning in125.81s. Two later added unit cases also pass in the final108-case focused run:589 distinct passing checks across these runs. No fresh full-backend/frontend/physical-backup result is claimed.

## Remaining work

Missing original import/provider facts,remaining financial and source completeness,unproven replies and explicit activation design/drills remain pending. Actual deployment/IAM/kernel egress/pilot evidence is separate. All work remains local: no commit,push,deploy,production source/config/flags/grants,real credential opening,AWS/provider call or purchase.

Owned replica PID7078,matching owner manifests/private storage removed after confirming only admin/config/local databases remained;zero temporary databases,27028/27029/6389 closed,no Redis,user Mongo1735 preserved.28 earlier source/test/cache fingerprints unchanged;31 final fingerprints match. Three specs/runbook/report match Desktop copies,158links/45release reports/eight private backups verified. Session memory updated last.
