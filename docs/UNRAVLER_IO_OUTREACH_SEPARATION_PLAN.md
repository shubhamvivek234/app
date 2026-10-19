# Outreach separation plan: standalone app on its own domain

Status: proposal (2026-10-19). Nothing here is implemented. Findings marked **[measured]** come from a grep survey of this repository on that date. Everything else is a recommendation or an assumption.

## 1. Decisions and recommended defaults

| Question | Recommendation | Why |
| :--- | :--- | :--- |
| GitHub repo | **New, separate repo**, created with history preserved (`git filter-repo`) | Separate release cadence, CI, secrets and access. A monorepo would keep the coupling you want to remove. |
| Vercel | **New Vercel project** for the outreach frontend, plus a second one (or the same one) for `outreach-site` marketing pages | Separate domain, env vars, previews and rollbacks. |
| AWS | **Same AWS account, separate resources**: new EC2, security group, Elastic IP, KMS key, IAM role | Satisfies "same AWS" without sharing blast radius. |
| EC2 host | **Do not co-locate** on the existing instance | It is a 913 MiB `t3.micro` that already froze under 9 containers. Outreach needs roughly 2–4 GiB (`t3.medium` class). |
| MongoDB | **Separate database, ideally a separate mongod** (container on the new host, or Atlas) | See section 4. |
| Redis / Celery | **Separate Redis and a separate Celery app** | Outreach already uses its own `outreach` queue. |
| Identity | **Separate users and workspaces in the new DB**; auth provider decision needed (section 5) | Outreach reads `users`, `workspaces`, `workspace_members` today. |
| Stripe | Separate webhook endpoint and product; pilot stays invoice-based | No checkout exists in the pilot today. |

## 2. What is coupled today [measured]

**Backend imports from outside `outreach/`** (count of import lines):
`db.mongo` 36, `utils.encryption` 18, `utils.roles` 6, `celery_workers.shutdown_handler` 6, `utils.free_llm_router` 4, `celery_workers.tasks` 4, `celery_workers.celery_app` 4, `utils.ssrf_guard` 3, `api.deps` 2, `utils.request_context` 1.

**Collections outside the `outreach_*` namespace** that outreach code touches: `users`, `workspaces`, `workspace_members`, `account_erasure_tombstones`, `account_invoice_guards`, `account_proxy_ip_guards`. The 78 distinct `outreach_*` collections found by `db.outreach_*` grep are already prefixed, which makes the data split mechanical. The grep only catches the literal `db.outreach_...` form, so run a second pass for collections referenced by string constant.

**Single database:** `DB_NAME` is one environment variable used by `db/mongo.py`, `db/indexes.py` and `api/main.py`.

**Router mount:** `api/main.py` includes `outreach.api.router`.

**Celery:** `celery_workers/celery_app.py` declares an `outreach` queue and includes `celery_workers.tasks.outreach`.

**Frontend:** `frontend/src/outreach/` is mostly self-contained. Its only imports outside the folder are `@/env` (2) and `@/components/UnravlerLogo` (1). The route is `/outreach/*` in `frontend/src/App.js`. Auth and API-client coupling was not found by grep. Check how the token is obtained before extraction.

**Not yet surveyed:** `mcp-server/`, `cli/`, `nginx/`, `k8s/`, the CI workflows, and any outreach hooks into the main app's billing or notifications.

## 3. Target architecture

```
 <newdomain>            -> Vercel project A: marketing (outreach-site)
 app.<newdomain>        -> Vercel project B: React app, /api/* rewrite -> api.<newdomain>
 api.<newdomain>        -> new EC2 (Elastic IP) -> nginx -> outreach API
                                     |-- outreach worker(s) + beat (Celery)
                                     |-- mongod (own DB) + redis (own)
                                     |-- egress gateway (see the IP plan)
 AWS KMS: new key + new workload role (outreach only)
 Old Unravler stack: unchanged until cutover, then outreach code removed
```

## 4. Database separation

1. **New database name** (for example `outreach_prod`), preferably a separate mongod so a runaway query or restore on one product cannot touch the other.
2. **Copy** all `outreach_*` collections plus the six shared collections above, **filtered** to the workspaces that move. Exclude everything else, including other users' data.
3. **Identity rows:** copy only the `users`, `workspaces` and `workspace_members` documents for the pilot workspaces. Strip fields that belong to the social-scheduling product.
4. **Indexes:** extract the outreach index definitions from `db/indexes.py` into the new repo's own index module. Several outreach features depend on strict, TTL-free unique indexes and the shared guard and snapshot transactions. These need a replica set (or a single-node replica set) in the new DB. Verify, do not assume.
5. **Erasure and tombstones:** `account_erasure_tombstones` and the guard collections are authority records. Migrate them with the data, or you can resurrect erased people.
6. **Verification:** per-collection document counts and checksums, then a read-only application smoke test against the copy, before any cutover.

## 5. Identity, auth and encryption

**Auth provider (needs your decision).**
- *Option A:* new Firebase project for the new domain. Cleanest separation, no SSO, users re-register or are invited.
- *Option B:* same Firebase project with the new domain added as an authorized domain. One login across both products, but the products stay coupled at the identity layer.
- Recommended for a separate product: **A**, unless you want existing Unravler users to sign in without re-registering.

**Encryption key.** `utils/encryption.py` uses a single Fernet key. Reusing it keeps both products readable by one secret. Generate a **new** key for the new app.

**Stored credentials (LinkedIn session cookies, proxy credentials, provider keys).** Migrating them means decrypting with the old key or KMS context and re-wrapping with the new one, including scoped `uc1:` ciphertexts bound to workspace context. Simplest safe path for a small pilot: **do not migrate session cookies**. Require reconnection, which is consistent with the fail-closed posture. Proxy leases and inventory records can move because they are metadata, but their credential fields need the same decision.

**KMS.** New key and new IAM role scoped to the new instance. Keep the `OUTREACH_KMS_*` settings validation as is.

## 6. What else must be separated

| Area | Action |
| :--- | :--- |
| Celery / Redis | New Celery app containing only the outreach tasks and `shutdown_handler`. Separate Redis. |
| Shared utils | Copy `encryption`, `roles`, `ssrf_guard`, `request_context`, `free_llm_router`, `deps` into the new repo. Do not publish a shared package yet. The duplicate code is small and the products will diverge. |
| LLM routing | `free_llm_router` is used for outreach AI. Decide whether the new app has its own provider keys and budget. |
| Secrets | New `.env`: Mongo, Redis, Fernet, KMS, IPRoyal/Webshare, Stripe, email, LLM keys. Never copy the old `.env` wholesale. |
| Email | New domain needs SPF, DKIM and DMARC for any transactional or mailbox features. |
| OAuth redirect URIs | Gmail/Outlook mailbox integrations and any other OAuth app need the new redirect URLs and re-verification. |
| CORS, cookies, CSP | Replace `unravler.com` origins with the new domain. The existing `vercel.json` rewrite targets `api.unravler.com`. |
| Webhooks | New signing secrets and new endpoint URLs. |
| Monitoring | New alert routes and log groups so outreach incidents do not page the other product. |
| CI | New workflows. Carry over the outreach backend, native-Mongo and browser contract jobs and the dependency and container scans. |
| Docs and legal | Update privacy, terms, billing, cookies and deletion pages. `outreach-site` already has these pages. |
| Session memory | Move the outreach portion of `AGENTS.md` into the new repo and keep it under its 80-line rule. |

## 7. Phased plan

**Phase 0: decisions (1–2 days).** Domain name. Auth Option A or B. Which workspaces migrate (pilot only, or all). Whether existing users keep access to both products. Whether outreach keeps the Unravler brand. Budget for a second host.

**Phase 1: extract the repo (2–4 days).**
- `git filter-repo` to keep `outreach/`, `frontend/src/outreach/`, `outreach-site/`, related `tests/`, `docs/UNRAVLER_IO_*` and `docs/OUTREACH_*`.
- Add the copied shared utils, a minimal `db/mongo.py`, a minimal Celery app, a slim `api/main.py` that mounts only the outreach router, and a frontend shell with its own `index`, routing and `@/env`.
- Goal: the existing outreach test suite passes in the new repo unchanged.

**Phase 2: decouple (3–7 days).**
- Replace imports of the old product's modules with local copies.
- Introduce an auth adapter and decide how `users`, `workspaces` and `workspace_members` are created in the new DB (invite-only, matching the pilot).
- Rename environment variables and cookie and domain constants.
- Remove any dependency on the main app's billing and notification paths.

**Phase 3: infrastructure (2–4 days).**
- New EC2 (start at 4 GiB RAM), Elastic IP, security group (443 and 80 only, SSH from your IP only), IMDSv2 required, EBS backups.
- Docker Compose for api, worker, beat, mongo, redis, nginx. Build images in CI and pull them. Do not build on the host. The old host's failed builds are the lesson.
- New KMS key and role. Route 53 or registrar DNS for `api.`, `app.` and the apex.
- Two Vercel projects connected to the new repo.

**Phase 4: data migration rehearsal (2–3 days).** Run the filtered copy into a staging database. Verify counts, indexes, and erasure and tombstone integrity. Run the full outreach test suite and a browser journey against staging. Keep `OUTREACH_LIVE_ACTIONS_ENABLED=false`.

**Phase 5: cutover (1 day).**
1. Announce a freeze. Pause campaigns and senders in the old app.
2. Take final snapshots and copy the data.
3. Bring up the new stack with live actions still off. Verify `/health` and `/ready`.
4. Pilot users reconnect LinkedIn sessions. Re-verify proxy leases.
5. Point DNS. Enable live actions only after an explicit, separate decision.

**Phase 6: remove outreach from the old app (after a stable period).** Remove the router include, `/outreach/*` frontend route, the Celery queue and task module, outreach indexes, and the outreach env vars from the old Compose. Keep a read-only backup of the old outreach collections for an agreed retention period, then delete them under the erasure policy.

**Rollback:** until Phase 6, the old app still has the code and a snapshot. Rolling back means pointing the DNS back and re-enabling the old queue. After Phase 6 there is no rollback, so schedule Phase 6 deliberately.

## 8. Risks

- **Duplicate codebases for shared utils** will drift. Accept it for now, and write down which functions were copied.
- **Strong guarantees in the code depend on Mongo features** (transactions, majority reads, unique and TTL-free indexes). A different Mongo deployment must support them. Test it, don't assume.
- **Credential migration** is the highest-risk data step. Prefer re-connect over re-encrypt.
- **A second host and a second domain double the operations surface** (patching, backups, alerts, certificates).
- **The proxy and IP-allocation automation plan** (`UNRAVLER_IO_HARDENED_IP_ALLOCATION_PLAN.md`) is separate and should not be rolled into this move. Separate first, automate later.
- **Legal and brand:** a new domain with the same processing activities does not remove the compliance obligations already documented.

## 9. Rough cost and effort (estimates, not quotes)

- Engineering: about 2–4 weeks for one developer, mostly Phases 1–2 and data rehearsal.
- New EC2 in the same region: tens of US dollars per month for a `t3.medium` class instance, plus storage and data transfer. Check current AWS pricing before committing.
- Domain, Vercel (a second project may need a paid plan depending on team settings), email sending and monitoring are extra.

## 10. Decisions recorded 2026-10-19

1. **Auth:** new Firebase project for the standalone app (Option A).
2. **Users:** no real users exist yet. Migrate no user data. Create one tester account in the new project and give it a one-month paid-pilot grant through the normal operator-grant path once the new stack exists. Credentials are never stored in the repository, docs or `AGENTS.md`; the tester sets the password in the new Firebase project, and the account should use a fresh password, not one reused elsewhere.
3. **Domain:** use subdomains of the current domain for now (for example `outreach.<current-domain>` for the app and `outreach-api.<current-domain>` for the API). All origins, cookie domains, CORS lists, OAuth redirect URIs and webhook URLs must come from environment variables, so the later switch to a new domain is configuration only. Do not set cookies on the parent domain, so the two products stay isolated.
4. **Host:** create a second EC2 instance in the same AWS account and region with its own security group, Elastic IP, IAM role and KMS key. Start at 4 GiB RAM.
