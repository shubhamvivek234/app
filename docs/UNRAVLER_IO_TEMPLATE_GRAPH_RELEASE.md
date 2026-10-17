# Unravler.io v2.79 — Reviewed template sequence editing

Updated: 2026-10-17 IST. Bounded local implementation on main at `54378a0913f87b8fd0c01fbb98e8e56c39a2c19a`; uncommitted and undeployed. This follows [reviewed template metadata editing](UNRAVLER_IO_TEMPLATE_METADATA_RELEASE.md). The preceding v2.72–v2.77 source was pushed as54378a0 with successful automatic frontend builds; the user deferred the unreachable backend rollout. Current production fleet coherence is not established.

## User behavior

The Templates gallery offers **Edit sequence** for a supported custom template with a dedicated current graph review. The existing visual builder edits a local draft; **Save template sequence** applies the reviewed replacement to future template uses. Current workspace editors/admins use existing sequence:update permission, with the established unique-owner fallback. This remains shared workspace content; no creator-only override or new sharing policy is added.

Only nodes, edges, tree, compiled_dag, compiler_contract_version, template_revision, graph_updated_at and graph_updated_by change. Metadata, native/public/workspace/creator identity, creation information and unknown nongraph fields retain their BSON values. Independent campaign/version/task copies and historical original creation receipts stay intact. Intentional graph editing recompiles and can normalize source numeric representations; graph BSON is not claimed unchanged. Editing does not publish a campaign version, launch work or authorize execution.

## Original review and strict graph contract

Gallery GET computes graph_review from the original received BSON row before projection. A distinct template-graph-scope-v1 digest binds original actor, authenticated UID and resolved workspace. Captured native identity, revision and full-record digest bind the original template. Metadata/deletion proofs cannot substitute. Review grants neither update nor execution authority.

A reviewable original must have a nonempty matching visual tree and valid semantic source graph. Existing compiled_dag and compiler_contract_version must either both be absent or both be present. Present compiled data must pass the strict compiled contract, plain browser-value checks and full canonical equality against the current source compilation, including IDs, titles, configs, delays, roots, order and extra fields. Unsupported markers, boolean delays, malformed compiled IDs/order, isolated markers and unproven originals hold without silent repair. Legacy originals with both compiled fields absent may be reviewed from valid source.

PATCH /sequences/templates/{id}/graph-reviewed accepts only strict version/workspace/revision/digests, exact frozen graph_json and its UTF-8 SHA-256 input digest. Recursive duplicate JSON keys, nonfinite/unsupported values, unsafe numeric magnitude, coercion and extra request fields deny. Input is bounded to1,048,576 UTF-8 bytes before parsing; the existing shared graph bound is1,000,000 JSON bytes,20,000 items and depth12, with100 nodes and200 edges. A mandatory nonempty tree of at most100 nodes must flatten to the same execution graph as the shared compiler; semantic condition/path/delay/config checks remain authoritative. JSON/browser numeric values must stay within JavaScript's safe integer magnitude, including BSON Int64 compatibility on original reads.

## Transaction and current authority

One shared workspace guard/snapshot/majority transaction rechecks the unique native current user for the original actor/UID, current member role or unique owner, active/open workspace and erasure tombstone. Existing user/member/owner authority counter writes fence concurrent changes. The bounded scoped lookup denies ambiguous scalar public identities; captured original native identity/revision/full-row proof must match. A copied literal full-row CAS replaces the original, then exact BSON readback must match before commit. Mongo object equality alone is not strict BSON-byte equality; the tested reread/fingerprint and write-conflict controls supply that protection.

Revision absence is legacy0. Every accepted update increments once, including equivalent graphs. The final increment may reach the JavaScript safe integer ceiling; later edits remain unavailable. Latest UTC-millisecond/public-actor audit fields replace previous graph audit fields. The established1MB original/prepared full-BSON limit is checked after load/encoding, not a strict database read-memory limit.

No new collection, index, receipt journal, execution grant, provider task or production migration is added. Original v2.76 creation retry/status remains historical after graph changes and does not recompile, overwrite newer content or recreate deleted templates. Guarded erasure removes the full row. Unknown commit acknowledgement returns a sanitized hold, with no automatic write replay.

## Browser fencing and uncertain outcomes

Template mode supplies the actual received visual tree to SequenceCanvas, copies it and validates it before first display. Missing, malformed or hidden-invalid trees do not substitute a starter graph. Conflicting campaign/template context denies. Template mode skips campaign reads, node-count reads, campaign persistence/autosave, legacy prompt-library writes and placeholder preview controls. Existing campaign mode retains its earlier behavior. Explicit supplied-sample SequenceReview stays available and performs no provider work.

Save captures and copies the current visible tree/nodes/edges before hashing exact JSON. A synchronous latch, original props/token and mount checks fence preparation, transport and completion. The canvas unmounts during preparation, pending and unknown states. A definite pretransport preparation failure retains an editable draft for correction.

Only exact HTTP200 with matching original scope/native/revision/input and next revision plus valid resulting server digests confirms completion. Compiler/full-BSON digests are server assertions, not browser reconstruction or signed external proof. Use, Delete and metadata editing share the same gallery operation lock. Success fetches a fresh catalog before further operations. Any malformed/extra/uncertain response holds; explicit single-flight current-token HTTP200 GET reload inspects current state without replaying PATCH or claiming the earlier edit succeeded merely because content matches.

Drafts and edit holds remain memory-only. Full unmount, browser/tab loss, raw scripts, cross-tab coordination, old writers, restored backups and the original catalog100-row/sequential-read constraints remain limits. No durable edit request locator, outcome history, cancellation, immutable version history or previous-graph restore is introduced.

## Verification and provenance

The final new backend selection passes91 checks:46 pure and45 native, zero skips,17.92 seconds. It covers recursive JSON duplicates/Unicode/browser numeric bounds; malformed original compiled contracts; scope/native/content/revision/creator drift; graph/metadata/delete races; current and post-snapshot role/UID/owner changes; exact BSON preservation/readback/full-row limits; rollback; actual guarded erasure; standalone denial; commit-acknowledgement loss; and original creation receipt behavior.

Fresh broad application checks pass3,963 with1,899 historical/opt-in skips, six sandbox deselections and11 warnings in332.39 seconds. The complete30-module native suite passes1,107 with zero skips and three warnings in635.91 seconds. Passing test identities have zero broad/native overlap:5,070 distinct backend passes; the focused91 and354 selections overlap those totals and are not added again. The whole frontend passes442 checks across52 suites in14.309 seconds.

Focused coverage passes354 overlapping checks in157.44 seconds: core119/123 statements (97%), sequence API166/222 (75%), combined285/345 (83%). The37 final new UI checks across four suites pass in1.525 seconds and cover the real canvas, helper, editor and gallery. Their measured new editor/helper coverage is96.49% statements,98.18% lines and95.68% branches; canvas/parent changes are also exercised by existing suites. All41 compiled synthetic-API browser journeys pass in70.266 seconds, including three new graph-edit journeys. These use loopback synthetic responses and do not prove authenticated live provider/source fidelity.

The CI-mode production frontend build passes with existing dependency/Tailwind/source-map warnings. Python compilation, configured medium/high scoped Bandit (zero findings) and diff checks pass. CI native selection now includes30 modules and minimum1,107 passing cases with zero skips. Remote CI/security/protected-check enforcement is not verified here.

Independent backend source/test review approves after correcting malformed original compiled-graph admission, with46 pure checks independently rerun. Independent frontend source/test review approves with37 checks rerun. Two whole frontend runs exposed asynchronous native WebCrypto assertion races in component/gallery tests; both now await actual digest promises without weakening assertions or changing production code. Independent review and37-check reruns approve those corrections; the fresh whole suite passes. Independent semantic document review approves the bounded claims; final numerical/private evidence review is recorded in the verification manifest.

Private backup/evidence: /tmp/unravler-template-graph-izn0pm. Earlier pre-final test runs remain historical. Verification checks19 frozen source/test/config/document hashes,23 preserved earlier-release hashes,23 Desktop pairs from20 source documents,318 local links,1,727 protected tracked baseline files and nine historical unrelated artifact fingerprints. Session memory is updated last, after final review. Final-verification.json records identities, final numerical approval, cleanup and memory hash.

## Rollout and remaining work

Keep this slice local. Prior backend deployment remains deferred by the user. Before a separately authorized rollout, drain/replace older template writers and use matching backend/frontend contracts; mixed or raw writers do not inherit this guarded protocol.

Next inspect sharing/ownership and durable recoverable edit/delete outcomes with immutable revision history. Broader team/sender governance, trustworthy sources/recipient contracts, security backlog, legacy migration, authenticated restore/reconciliation, activation, live health/IAM-egress and a real pilot remain separate gates. Existing live/conditional defaults stay false. No commit, push, deploy, production migration, real provider/AWS call, grant, purchase or live flag change occurred in this continuation.

