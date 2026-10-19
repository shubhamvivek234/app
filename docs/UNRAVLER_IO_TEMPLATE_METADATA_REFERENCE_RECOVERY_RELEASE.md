# Unravler.io v2.83 — Same-tab template-details recovery

Updated: 2026-10-18 IST. Bounded frontend-only implementation against committed baseline `e63bcfe`. The preceding [v2.81–v2.82 deployment](UNRAVLER_IO_V2_82_DEPLOYMENT.md) remains separate. This slice has not been committed or deployed.

## Behavior and storage

Template-details updates now save and reread an original request locator in sessionStorage before the existing POST. Reloading or returning to Templates offers an explicit **Check saved details update status** action. Recovery requests a fresh current-account/workspace context, then GETs only its matching original request with its original input hash. It never resubmits edited content or automatically creates another request.

The dedicated `unravler.outreach.templateMetadataReferences.v1` envelope permits at most ten locators and 8,192 UTF-16 code units. Each locator contains only contract version, workspace ID, operation scope digest, canonical request UUID and exact input digest. No name, description, graph, original review proof, template ID, token or separate Firebase UID is persisted. Workspace identifiers and hashes remain linkable metadata. Existing creation-reference storage is untouched.

Malformed, duplicate, full, blocked or unverifiable storage denies new transport. A locator stored before a crash without POST can remain held indefinitely when status returns404. There is no eviction, cancel/tombstone protocol or fresh-UUID escape. Browser/tab/sessionStorage loss, manual deletion, raw scripts and cross-tab coordination remain limits; this is not durable browser-wide history.

## Scope and concurrency

Gallery Use, details edit, sequence edit and deletion are disabled while restored metadata recovery needs checking. Each handler also has a synchronous storage guard to catch references written after the last render. Fresh matching context and exact HTTP200 strict receipt validation are required for confirmation. Current-token, gallery-generation and mount fences reject stale asynchronous results. Leaving and reentering the gallery resets context admission.

Foreign-scope locators remain in storage; explicit current-context inspection can permit the current account's actions without querying foreign original status. A retained original missing from storage is restored before another scope can unlock. If another mounted view already stored a newer same-scope request, stale cleanup preserves it and a subsequent explicit check can inspect the newer UUID. Cleanup compares the original locator, verifies its write and rereads storage before unlocking. Cleanup failure, non200 responses, malformed/foreign receipts and unknown results retain the hold.

Live editor confirmation retains the stricter in-memory original native/revision/review proof comparison. Reload recovery has only the locator: it validates the exact receipt schema, original locator/input, custom-template identity, safe integer revision increment and hash fields returned by the current-authority server status endpoint. That server assertion confirms a historical update, not current template content or immutable revision history. After confirmation the gallery reloads current templates and reviews.

## Verification

- Test-first failure recorded before implementation in `red.log`.
- Whole frontend:563 tests across56 suites pass; affected final run:89 tests across4 suites, overlapping the whole suite. This adds49 frontend tests over the514-test baseline.
- Selected new/extended hook and utility coverage:94.77% statements,99.02% lines,92.03% branches.
- Production build passes in64.62s with existing dependency/source-map, Tailwind and bundle-size warnings. Scoped hook-rule/unused-variable lint passes with a tooling deprecation warning.
- Unchanged backend metadata policy/receipt unit contracts:63 pass, one existing warning. Backend source/schema/collections and authority/erasure contracts were not changed; full backend/native suites were not freshly rerun.
- All46 compiled synthetic-API browser journeys pass in30.1s, including two new reload cases: lost-response/current-template replacement and the write-ahead/no-receipt crash window. These journeys do not verify real login, providers or production integration.

Independent frontend source review found a newer-reference recovery dead end; it was corrected and independently rerun. The final review evidence is in `/tmp/unravler-metadata-reference-9jd4XS/independent-frontend-final.log`. Browser runs exposed premature request-count assertions in metadata/sequence missing-status tests; they now await actual request observation and completed checking, retaining exact counts and hold assertions. Historical failed logs/traces remain in the evidence directory.

## Remaining work and release limits

Next: same-tab persistent sequence-update and deletion locators, then sharing/ownership requirements and immutable template revision history. Current sequence-edit/deletion references still remain view-memory-only. Broader source/recipient fidelity, team/sender governance, security/legacy migration, authenticated restore/reconciliation/reactivation, controlled integration/health/IAM-egress verification and an actual pilot remain open.

No commit, push, deployment, production migration, live flag change, provider/AWS request, grant or purchase was performed for this slice. The completed backend-deployment retry automation was paused to prevent its obsolete instructions from rerunning. The three architecture specifications, implementation roadmap and corresponding Desktop copies are synchronized; session memory is updated last.
