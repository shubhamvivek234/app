# Unravler.io v2.86 — Workspace template access

Updated: 2026-10-19 IST. Local implementation against HEAD `e63bcfe`, preserving uncommitted [details](UNRAVLER_IO_TEMPLATE_METADATA_REFERENCE_RECOVERY_RELEASE.md), [sequence](UNRAVLER_IO_TEMPLATE_GRAPH_REFERENCE_RECOVERY_RELEASE.md) and [deletion](UNRAVLER_IO_TEMPLATE_DELETION_REFERENCE_RECOVERY_RELEASE.md) reference recovery. The earlier [production rollout](UNRAVLER_IO_V2_82_DEPLOYMENT.md) is separate. This slice is uncommitted and undeployed.

## Sharing and ownership policy

Custom templates remain shared resources of their current workspace. The recorded creator is attribution, not a personal owner, extra deletion permission, ownership transfer or cross-workspace access path. Another permitted workspace editor may edit them. Existing workspace roles govern:

| Current role | Inspect catalog | Configure a draft | Edit custom details/sequence | Delete custom template |
| --- | --- | --- | --- | --- |
| Owner or admin | Yes | Yes | Yes | Yes |
| Editor | Yes | Yes | Yes | No |
| Viewer or client | Yes | No | No | No |

Built-in templates may be configured by permitted roles but cannot be edited or deleted. Graph compatibility, current permissions and execution authority remain distinct: a compatible graph can still be view-only, and configuring a draft never launches it. Viewer inspection means names, descriptions, step counts and compatibility in the catalog; this slice does not add a read-only graph canvas.

There are no public links, external shares, private visibility toggles, creator-only overrides, ownership transfers or new sharing grants. Per-user/offboarding erasure and workspace ownership retain their existing contracts; this slice does not redesign them. These optional extensions need separate product/access/retention contracts. Immutable template revision history is the next planned implementation.

## Implementation and limits

The gallery adds an eight-field `workspace_access` observation: version, current workspace, built-in/workspace visibility, creator-is-current-actor boolean, configure/edit/delete booleans and `execution_authorized=false`. Stored template fields cannot override this computed descriptor. Configure requires existing campaign-create and sequence-update permissions; editing/deletion use their existing sequence permissions. Native/full-record reviews and receipts are unchanged.

The new access helper reads at most two candidate user, UID, membership or owner records per lookup. It rejects observed duplicate/array-alias identities, missing or inactive users/members, mismatched original UID, identity-erasure tombstones and a closed workspace. Membership takes priority over owner fallback. Fallback requires one current matching owner record. Both identity observations recheck exact plain-text actor/UID/status; BSON Code roles, statuses and owner identities cannot masquerade as ordinary recorded authority. Database failures return sanitized503 without a successful partial starter catalog.

These reads are sequential observations, without snapshot/response-time authority, global raw-writer uniqueness, completeness or revocation guarantees. Permission changes after observation may cause a later action to be rejected. Existing mutation dependencies and native transactional UID/role/erasure/revision guards remain authoritative and unmodified. The new helper and gallery handler add no writes, sessions, authority counters, collections, indexes or grants. Existing authentication/workspace hydration can still update or bootstrap profiles/workspaces; the complete authenticated request is not claimed to be write-free.

The browser requires the exact descriptor schema, booleans and supported built-in/custom relationship before enabling controls. Missing, malformed, extra or unsupported metadata keeps that row visible with **Access needs review** and disabled controls. **Workspace template**, optional **Saved by you**, and **Built-in template** labels clarify scope. **Reload templates** explicitly refreshes observed roles while respecting active editor/deletion/use work. Existing details/sequence/deletion recovery holds remain intact; creation recovery remains separately governed by the wizard.

The catalog is bound to its captured token. Token changes during loading cannot publish old access; changed tokens block opening editors or using an earlier catalog. Token/view/mount checks stop subsequent Use requests and navigation. They cannot undo an already-issued draft/sequence write, guarantee cookie-only identity changes, detect every same-token workspace change, or supply cross-tab coordination. Server endpoints still authorize their current workspace. Ordinary Use retains its existing two-request partial/unknown-draft limits.

## Verification and provenance

Evidence: `/tmp/unravler-template-workspace-access-5trs92ld`; baseline1,803 tracked/nonignored regular files. Missing-module test-first failures are in `red-backend.log` and `red-frontend.log`. New stale-token tests failed before the catalog fence. Independent review then reproduced identity-reread drift; `review-red.log` records two failures before correction. Historical fixture assertions remain; their synthetic catalogs now supply the new explicit access shape.

Final frontend:680 passing checks across60 suites, zero failures/skips,10.066s;23 new access checks over the prior657. The focused utility/page checks overlap this total. Selected new helper coverage is19/19 statements,16/16 lines,33/33 branch arms and5/5 functions; this is not whole-gallery/application coverage. All53 compiled synthetic browser journeys pass in55.0s, including three new editor/viewer/old-contract journeys and explicit role reload. Browser APIs/authentication are synthetic.

Backend:301 passing template checks, zero skips, one existing multipart warning,7.76s;177 real local Mongo checks across access/governance/metadata/graph modules, zero skips, one existing warning,63.25s. There are36 new pure access cases and17 new native/API cases. New core coverage is51/52 statements98.08% and22/22 branches100% (branch-inclusive98.65%). No full application or complete historical native suite was freshly rerun. Native identities are synthetic, and local HTTP testing does not establish real Firebase/provider fidelity.

Production build passes in70.29s with existing dependency/source-map/Tailwind/bundle warnings. Python compilation, scoped medium/high Bandit with no findings, scoped frontend lint and whitespace checks pass. Independent Python review reran36 cases, reviewed all17 new native cases and verified ten mutation/transaction/role files unchanged. Independent final frontend review reran23 checks and approved. Final evidence/document review checks frozen hashes, counts, baseline changes, document links and eight Desktop copies before session memory is written last.

One coverage command omitted its private data-file location and overwrote ignored root `.coverage`. The new data was moved into the evidence directory, and root coverage was restored from three agreeing pre-existing saved copies to SHA256 `4b74da9b0ce92d241eb136c8d09b5716e661366ef11ff2f8a1bf666257de94ba`; the restoration is documented in `coverage-preservation.json`. Final branch coverage uses an explicit private `COVERAGE_FILE`.

## Rollout and remaining work

Deploy the additive backend descriptor before this frontend when release is separately requested. An older backend cannot supply the required observation, so the new frontend holds its template controls until the backend is updated and the catalog reloaded. Existing mutation authority, live flags and deployment state are unchanged here.

Next: immutable template revision history. External/private sharing and transfers remain separate requirements. Source/recipient fidelity, team/sender governance, security/legacy migration, authenticated restore/reconciliation/reactivation, integration/health/IAM-egress verification and an actual pilot remain open. No commit, push, deployment, production migration, live flag change, provider/AWS call, grant or purchase occurred. Three architecture specs, roadmap and matching Desktop copies are synchronized; session memory is updated last.
