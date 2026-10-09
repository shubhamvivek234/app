# Unravler.io v2.44 — stopped proxy assignment consistency review

Date: 2026-10-09. Local, uncommitted and undeployed.

## Scope

The private restore inventory now reviews selected lease-to-asset-to-sender metadata relationships. It reports malformed asset/sender identity, multiple leases per sender, missing candidate asset, conflicting current/sticky workspace, unsupported or mismatched provider/country, missing/ambiguous installed sender, changed sender proxy ID and unproven/mismatched proxy credential generation. Missing sender is review-required rather than established loss: a pending reservation may have no installed account.

A local_lease_links_match finding means only that selected metadata links agree. It does not prove physical IP uniqueness, paid availability, Webshare import/lifecycle lineage, credential decryption or validity, provider ownership, sender authentication, active capacity or deployment readiness. Candidate inventory includes last_workspace_id rows; sticky/current scope contradictions now require review. Scope absence and omitted external facts never certify ownership. Multiple leases prevent a local match; independently reported missing assets remain visible. sender/account linkage uses the application id, not Mongo _id. References use the existing bounded reference validator before a local match: whitespace/control-only asset/sender IDs and generation strings are rejected.

New projections include inventory country_code/credential_generation, lease provider/country_code and account proxy.credential_generation. These enter the private snapshot digest, so previous digests can change. No credential ciphertext is selected by these additions. Secret-only changes leave digests stable; selected generation changes invalidate them. Output remains aggregate counts/findings with private linkable digests, without raw invoice/IP/account/lease/credential material.

The v2.42/v2.43 stopped contract remains: matching prepared execution epoch, all five flags off, explicit all-writer/cache drain assertion, same guard/snapshot/majority session, seven selected collections with100 rows each and65,536 reviewed metadata bytes checked after reads. Existing guard/root/journal fence counters may advance. These limits are not wire/memory bounds, a fleet census or source completeness proof. No lease, account, credential, reservation, financial state, held owner/token/receipt or unknown outcome is altered. No new schema/index/journal/CLI apply command, grant, activation, retry, refund or provider action.

## Verification

78 focused checks pass(58 unit/CLI+20 native Mongo)in17.17s;21 new cases(14unit+7native). Coverage99%combined(core99%,CLI97%). New cases cover matching links, pending/no-account review, ambiguous legacy accounts, foreign/sticky scope, provider/country disagreement, changed proxy/generation, malformed references and multiple leases. Native tests preserve exact resources/accounts/reservations and physical evidence. Duplicate-account cases deliberately use an index-free legacy fixture; they do not claim the production unique account index permits duplicates. Existing snapshot, capacity, stopped-policy, native financial bindings and standalone-denial checks remain included.

Independent review identified contradictory sticky scope and malformed reference false matches; both were fixed and regressions added without changing shared fixtures or weakening guards. Final independent Python review approves;58 independent unit/CLI cases pass and scoped Bandit is clean. Compile/scoped Bandit/whitespace pass. Final restore suite:559 passed,2 opt-in physical-backup drills skipped,one existing warning in106.55s. No fresh full-backend, frontend or physical-backup result is claimed.

## Remaining boundaries

This selected local consistency report does not authenticate/recover missing outside-backup provider/financial facts, inspect every provider operation, prove source completeness or settle unproven reply evidence. Explicit activation design/drills and actual deployment/IAM/kernel egress/pilot checks remain pending. All work remains local: no commit,push,deploy,production source/config/flags/grants,real credential opening,AWS/provider call or purchase.

Owned replica PID2834, matching owner manifests and private storage were removed after confirming only admin/config/local databases remained. No temporary databases remain;27028/27029/6389 are closed,no Redis was started,user Mongo1735 is preserved. All28 unchanged earlier source/test/cache fingerprints remain intact;31 final fingerprints match. Three specs/runbook/report byte-match Desktop copies;152 spec links/43 release reports and eight private backup copies verify. Memory updated last.
