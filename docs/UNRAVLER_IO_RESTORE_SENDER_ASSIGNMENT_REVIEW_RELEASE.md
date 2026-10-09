# Unravler.io v2.48 — stopped sender-to-proxy assignment review

Date: 2026-10-10. Local, uncommitted and undeployed.

## Scope

The private restore inventory now checks the reverse direction of assignment: selected account/application-sender ID → proxy asset → lease. It reports malformed sender/proxy references,duplicate application identities,multiple selected accounts sharing a proxy,missing or contradictory current/sticky-scope assets,missing/ambiguous leases,wrong lease sender,multiple leases for one sender,provider/country disagreement and missing/changed proxy credential generation. A sender whose asset/lease is absent was previously only counted; the missing reverse link now explicitly requires review.

local_sender_assignment_links_match means only that selected metadata links agree. It does not validate sender authentication,credential contents,proxy health,paid term,original import/adoption/lifecycle lineage,physical IP uniqueness,provider ownership or permission to use the asset. Other financial/import/adoption/lifecycle/binding findings remain independent; matching this group cannot cancel another finding or certify a complete inventory. A sender without an installed assignment,including stopped/legacy/draft states,can legitimately require review; the report does not label it active,delete it or invent ownership. Application id is used for sender linkage,not Mongo _id.

The check reuses existing projections and nine collections; no new field/collection/schema/index/journal/CLI command is introduced. Existing100rows-per-collection/whole65,536 reviewed metadata bytes after reads,same guard/snapshot/majority session,matching prepared stopped epoch,five flags off and asserted all-writer/cache drain remain. After-read limits are not wire/memory bounds or a fleet census. Guard/root/journal fence counters may advance; domain assets/accounts/leases/reservations/credentials,financial state and held unknown owner/token/receipt evidence remain intact. New findings may change prior inventory digests.

Output stays aggregate counts/findings with private linkable snapshot digest,without raw sender/resource/credential material. Secret-only account changes remain excluded; selected proxy-link changes bind the digest. Every result keeps activation_allowed/completeness_verified/provider_ownership_verified false. No grant,activation,replay,refund,credential opening or provider action occurs.

## Verification

150 focused checks pass(107 unit/CLI+43 native Mongo)in31.77s,24 new cases(16unit+8native);99%combined coverage(core99%,CLI97%). Initial11 red unit cases preceded implementation. New cases cover matching chains,missing asset/lease,wrong sender,duplicate identity,shared proxy,malformed references,foreign/sticky asset,ambiguous/multiple leases,provider/country and generation conflicts. Native cases cover both provider labels,reverse-only gaps,shared/duplicate accounts,sticky scope,exact resource/reservation/account/physical evidence preservation,secret-only digest stability and selected-link digest changes. Duplicate/shared legacy native fixtures are index-free; they do not claim production unique indexes allow those states. Matching Webshare link metadata does not establish valid import metadata or operational provider readiness. Independent Python review approves;107 independent unit/CLI cases pass,eight native contracts inspected without service actions. Compile/scoped Bandit/whitespace pass. Final restore suite:631 passed,2 opt-in physical-backup drills skipped,one existing warning in129.03s. No fresh full-backend/frontend/physical-backup result is claimed.

## Remaining work

Authenticated outside-backup source/provider/financial facts and completeness,unproven reply evidence,explicit new-epoch activation design/drills and actual deployment/IAM/kernel egress/pilot evidence remain pending. This report neither repairs a relationship nor authorizes use. All work remains local: no commit,push,deploy,production source/config/flags/grants,real credential opening,AWS/provider calls or purchase.

Owned replica PID15154,matching owner manifests/private storage removed after confirming only admin/config/local databases remained;zero temporary databases,27028/27029/6389 closed,no Redis,user Mongo1735 preserved.28 earlier source/test/cache fingerprints unchanged;31 final fingerprints match. Three specs/runbook/report match Desktop copies,164links/47release reports/eight private backups verified. Session memory updated last.
