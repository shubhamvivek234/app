"""Account-local installation fence, bounded custody, and drained connection repair."""
from datetime import datetime, timedelta, timezone
import logging

from pymongo.errors import DuplicateKeyError

from outreach.core.authorization import canonical_hash
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.inbox_freshness import credential_generation
from outreach.core.manual_resolution import require_review
from outreach.core.paid_access import _utc, get_active_entitlement
from outreach.models import OutreachAccount

PENDING_SECRETS = {key: "" for key in ("li_at_enc", "jsession_id_enc", "li_a_enc")}
ACCOUNT_SECRETS = {key: "" for key in ("session_cookie_enc", "encrypted_session_cookie", "jsession_id", "li_a_enc", "li_at_enc", "jsession_id_enc")}
ACTIVE_JOBS = ["queued", "running", "finalizing", "repairing"]
RECONNECT_COOLDOWN_REASONS = frozenset({"rate_limited_429", "commercial_limit", "proxy_unhealthy"})
logger = logging.getLogger(__name__)


def installed_digest(account: dict) -> str:
    return canonical_hash({key: account.get(key) for key in ("session_cookie_enc", "jsession_id", "li_a_enc")})


def credential_deadline(job: dict) -> datetime | None:
    start = _utc(job.get("custody_started_at")) or _utc(job.get("created_at"))
    captured = _utc(job.get("custody_expires_at"))
    if not start:
        return captured  # Legacy missing custody metadata is expired by the sweep.
    deadline = start + timedelta(minutes=15)
    return min(deadline, captured) if captured else deadline


def captured_after_disconnect(account: dict, job: dict) -> bool:
    """Only a fresh, explicit reconnect can follow a recorded disconnect."""
    if "connection_disconnected_at" not in account:
        return True
    stopped, captured = account.get("connection_disconnected_at"), job.get("custody_started_at") or job.get("created_at")
    if not isinstance(stopped, datetime) or not isinstance(captured, datetime):
        return False
    return _utc(captured) > _utc(stopped)


def verified_connection_state(account: dict, now: datetime) -> dict:
    """A new session proves authentication, never overrides a platform hold."""
    reason, raw_deadline = account.get("stop_reason"), account.get("cooldown_until")
    deadline = _utc(raw_deadline) if isinstance(raw_deadline, (datetime, str)) else None
    valid_deadline = raw_deadline is None or deadline is not None
    elapsed = deadline is not None and deadline <= now
    clearable = (reason is None or type(reason) is str and (
        reason == "session_expired" or reason in RECONNECT_COOLDOWN_REASONS and elapsed))
    if valid_deadline and (raw_deadline is None or elapsed) and clearable:
        return {"status": "active", "stop_reason": None, "stopped_at": None,
                "cooldown_until": None, "error_details": None}
    return {"status": "checkpoint_detected"}


class ConnectionRepair:
    def __init__(self, db) -> None:
        self.db = db

    @staticmethod
    def scope(job: dict) -> dict:
        return {"id": job["id"], "workspace_id": job["workspace_id"]}

    @staticmethod
    def account_scope(job: dict) -> dict:
        return {"id": job["sender_id"], "workspace_id": job["workspace_id"]}

    async def prepare(self, job: dict, owner: str, generation: str, profile: dict,
                      *, now: datetime | None = None) -> None:
        """Create no usable session. A stopped job cannot cross the later install CAS."""
        now = now or datetime.now(timezone.utc)
        deadline = credential_deadline(job)
        if not deadline or deadline <= now:
            raise ValueError("Credential custody expired")
        owned = {**self.scope(job), "status": "running", "verification_owner_token": owner}
        current = await self.db.outreach_connection_jobs.find_one(owned)
        lock = await self.db.outreach_connection_locks.find_one({"_id": job["sender_id"],
            "workspace_id": job["workspace_id"], "job_id": job["id"]})
        if not current or not lock:
            raise ValueError("Connection owner changed")
        account_scope = self.account_scope(job)
        account = await self.db.outreach_accounts.find_one(account_scope)
        if account and not captured_after_disconnect(account, job):
            raise ValueError("Sender was disconnected after verification was captured")
        base = account.get("credential_generation") if account else None
        if account and (account.get("is_deleted") or (job.get("reconnect") and (
                account.get("linkedin_urn") != profile.get("linkedin_urn")
                or "base_credential_generation" in job and job["base_credential_generation"] != base
                or job.get("base_sender_generation") and job["base_sender_generation"] != credential_generation(account)))):
            raise ValueError("Reconnect account changed")
        prior_fence = (account or {}).get("connection_finalization")
        if prior_fence and prior_fence.get("state") in {"prepared", "installed"}:
            raise ValueError("Another finalization requires repair")
        fence = {"job_id": job["id"], "owner_token": owner, "generation": generation,
            "base_generation": base, "state": "prepared", "ever_installed": False,
            "custody_expires_at": deadline, "expected_linkedin_urn": profile.get("linkedin_urn")}
        # Write the prospective generation before account preparation. An
        # interrupted preparation is quarantined even if no account write is visible.
        saved = await self.db.outreach_connection_jobs.update_one(owned, {"$set": {
            "finalization_prepared": True, "credential_generation": generation,
            "expected_linkedin_urn": profile.get("linkedin_urn"), "custody_expires_at": deadline,
            "custody_started_at": job.get("custody_started_at") or job.get("created_at")}})
        if not saved.matched_count:
            raise ValueError("Connection owner changed")
        if account:
            query = {**account_scope, "credential_generation": base, "is_deleted": {"$ne": True},
                "connection_finalization": prior_fence if prior_fence else {"$exists": False},
                "connection_disconnected_at": account.get("connection_disconnected_at", {"$exists": False})}
            for key in ACCOUNT_SECRETS:
                query[key] = account[key] if key in account else {"$exists": False}
            changed = await self.db.outreach_accounts.update_one(query, {"$set": {"connection_finalization": fence}})
            if not changed.matched_count:
                raise ValueError("Account finalization changed")
        else:
            stub = OutreachAccount(id=job["sender_id"], workspace_id=job["workspace_id"],
                user_id=job["user_id"], account_name=profile.get("account_name") or "LinkedIn sender",
                linkedin_urn=profile.get("linkedin_urn"), country_code=job["country_code"], status="reauth_required",
                created_at=now).model_dump()
            stub["_id"] = canonical_hash([job["workspace_id"], job["sender_id"]])
            stub["connection_finalization"] = fence
            stub.pop("credential_generation", None)
            try:
                await self.db.outreach_accounts.insert_one(stub)
            except DuplicateKeyError:
                raise ValueError("Sender account changed") from None
        if not await self.db.outreach_connection_jobs.find_one(owned):
            await self.close_fence(job, now=now)
            raise ValueError("Connection was stopped during preparation")

    async def install(self, job: dict, owner: str, generation: str, updates: dict,
                      *, now: datetime | None = None, prepared_proxy=None) -> bool:
        from outreach.core import suppression
        from outreach.core.restore_epoch import positive, EpochUnavailable
        async def apply(current):
            epoch = await positive(current, job['workspace_id'])
            result = await ConnectionRepair(current)._install_control(job, owner, generation, updates,
                now=now, prepared_proxy=prepared_proxy)
            if not epoch.live():
                raise EpochUnavailable('Restore configuration changed during installation')
            return result
        return await suppression.mutate_suppression(self.db, job['workspace_id'], apply)

    async def _install_control(self, job: dict, owner: str, generation: str, updates: dict,
                               *, now: datetime | None = None, prepared_proxy=None) -> bool:
        if (updates.get('proxy') or {}).get('provider') == 'iproyal_static':
            from outreach.core import suppression
            from outreach.core.dispatch_authority import AuthorityDatabase
            from outreach.core.proxy_identity import restore_ip_allowed
            authority = (AuthorityDatabase(self.db.database, self.db.session, 'iproyal-restore-install')
                         if isinstance(self.db, suppression.SuppressionDatabase) else self.db)
            inventory = await authority.outreach_proxy_inventory.find_one({
                '_id': job['proxy_id'], 'last_workspace_id': job['workspace_id']})
            if not inventory:
                return False
            hosts = [(updates.get('proxy') or {}).get('host')]
            if inventory.get('host') is not None:
                hosts.append(inventory['host'])
            for host in set(hosts):
                if not await restore_ip_allowed(authority, host):
                    return False
            return await ConnectionRepair(authority)._install(job, owner, generation, updates, now=now)
        if (updates.get('proxy') or {}).get('provider') == 'webshare_plan':
            from outreach.core import suppression
            from outreach.core.dispatch_authority import AuthorityDatabase
            from outreach.core.webshare_provisioning import managed_webshare_valid
            from outreach.core.proxy_custody import proxy_digest
            from outreach.core.paid_access import live_actions_enabled
            async def install(current):
                authority = (AuthorityDatabase(current.database, current.session, 'managed-webshare-install')
                             if isinstance(current, suppression.SuppressionDatabase) else current)
                workspace = job['workspace_id']; checked_at = now or datetime.now(timezone.utc)
                inventory = await authority.outreach_proxy_inventory.find_one({'_id': job['proxy_id']})
                lease = await authority.outreach_proxy_leases.find_one({'_id': job['proxy_id'],
                    'workspace_id': workspace, 'sender_id': job['sender_id'],
                    'provider': 'webshare_plan', 'country_code': job['country_code']})
                slot = await authority.outreach_sender_slots.find_one({'workspace_id': workspace, 'sender_id': job['sender_id']})
                if (not inventory or not lease or not slot or not live_actions_enabled()
                        or not await managed_webshare_valid(authority, inventory, workspace, now=checked_at)
                        or not await get_active_entitlement(authority, workspace, checked_at)
                        or proxy_digest(inventory) != proxy_digest(updates['proxy'])
                        or prepared_proxy is None or not prepared_proxy.matches(inventory, workspace)):
                    return False
                return await ConnectionRepair(authority)._install(job, owner, generation, updates, now=checked_at)
            return await suppression.mutate_suppression(self.db, job['workspace_id'], install)
        return await self._install(job, owner, generation, updates, now=now)

    async def _install(self, job: dict, owner: str, generation: str, updates: dict,
                       *, now: datetime | None = None) -> bool:
        from outreach.core.restore_epoch import positive
        epoch = await positive(self.db, job['workspace_id'])
        now = now or datetime.now(timezone.utc)
        current = await self.db.outreach_connection_jobs.find_one({**self.scope(job), "status": "finalizing",
            "verification_owner_token": owner, "credential_generation": generation, "custody_expired_at": {"$exists": False}})
        if not current:
            return False
        deadline = credential_deadline(current)
        if not deadline or deadline <= now:
            return False
        account = await self.db.outreach_accounts.find_one(self.account_scope(job))
        if account and not captured_after_disconnect(account, current):
            return False
        fence = (account or {}).get("connection_finalization") or {}
        if (fence.get("job_id") != job["id"] or fence.get("owner_token") != owner
                or fence.get("generation") != generation or fence.get("state") != "prepared"):
            return False
        query = {**self.account_scope(job), "connection_finalization": fence,
            "connection_finalization.custody_expires_at": {"$gt": now},
            "credential_generation": fence.get("base_generation"), "is_deleted": {"$ne": True},
            "$expr": {"$gt": ["$connection_finalization.custody_expires_at", "$$NOW"]}}
        await positive(self.db, job['workspace_id'], captured=epoch.captured)
        changed = await self.db.outreach_accounts.update_one(query, {"$set": {
            **updates, **verified_connection_state(account or {}, now),
            "credential_generation": generation, "connection_finalization.state": "installed",
            "connection_finalization.ever_installed": True, "connection_finalization.installed_at": now,
            "connection_finalization.installed_credential_digest": installed_digest({**account, **updates})},
            "$unset": {"encrypted_session_cookie": "", "li_at_enc": "", "jsession_id_enc": "", "proxy_config": ""}})
        return bool(changed.matched_count)

    async def close_fence(self, job: dict, *, now: datetime | None = None, _remaining: int = 3) -> dict:
        """Closing and installing contend on the same account document."""
        now = now or datetime.now(timezone.utc)
        if _remaining <= 0:
            raise ValueError("Account changed repeatedly; retain connection quarantine")
        account_scope = self.account_scope(job)
        account = await self.db.outreach_accounts.find_one(account_scope)
        fence = (account or {}).get("connection_finalization") or {}
        if fence.get("job_id") != job["id"]:
            return {"proven_uninstalled": False, "legacy": True, "account_absent": account is None}
        installed = bool(fence.get("ever_installed"))
        expected_generation = fence.get("generation") if installed else fence.get("base_generation")
        if account.get("credential_generation") != expected_generation:
            raise ValueError("Current account generation differs; retain connection quarantine")
        changes = {"connection_finalization.state": "closed", "connection_finalization.closed_at": now}
        update = {"$set": changes}
        if installed:
            changes.update(status="disconnected" if fence.get("completion") == "disconnected" else "reauth_required", updated_at=now)
            update["$unset"] = ACCOUNT_SECRETS
        changed = await self.db.outreach_accounts.update_one({**account_scope, "connection_finalization": fence,
            "credential_generation": expected_generation}, update)
        if not changed.matched_count:
            # An installation may have won this race; reread and scrub its exact generation.
            return await self.close_fence(job, now=now, _remaining=_remaining - 1)
        return {"proven_uninstalled": not installed, "ever_installed": installed}

    async def expire(self, job: dict, *, now: datetime | None = None, force: bool = False) -> None:
        now = now or datetime.now(timezone.utc)
        deadline = credential_deadline(job)
        if not force and deadline and deadline > now:
            return
        await ExecutionPermission(self.db).revoke(job["workspace_id"], job["sender_id"], "custody_guard", "connection_custody_expired", now=now)
        # Scrub pending bytes even if replacement account ownership prevents
        # an account repair. Keep a durable quarantine record for that conflict.
        changed = await self.db.outreach_connection_jobs.update_one({**self.scope(job), "status": job["status"],
            "verification_owner_token": job.get("verification_owner_token"), "credential_generation": job.get("credential_generation")}, {
            "$set": {"custody_expired_at": now, "needs_operator_repair": True, "updated_at": now}, "$unset": PENDING_SECRETS})
        if changed.matched_count:
            await self.close_fence(job, now=now)

    async def inspect(self, workspace_id: str, job_id: str) -> dict:
        job = await self.db.outreach_connection_jobs.find_one({"workspace_id": workspace_id, "id": job_id})
        if not job:
            raise ValueError("Connection job not found")
        account = await self.db.outreach_accounts.find_one(self.account_scope(job))
        lease = await self.db.outreach_proxy_leases.find_one({"workspace_id": workspace_id, "sender_id": job["sender_id"], "_id": job["proxy_id"]})
        slot = await self.db.outreach_sender_slots.find_one({"workspace_id": workspace_id, "sender_id": job["sender_id"]})
        physical = await self.verification_receipts(job)
        view = {"job": {key: job.get(key) for key in ("id", "workspace_id", "sender_id", "status", "credential_generation",
            "expected_linkedin_urn", "verification_owner_token", "proxy_id", "country_code", "created_slot", "new_proxy_reservation")},
            "account": {key: (account or {}).get(key) for key in ("credential_generation", "linkedin_urn", "status", "connection_finalization")},
            "credentials_present": bool((account or {}).get("session_cookie_enc") or (account or {}).get("encrypted_session_cookie")),
            "repair": job.get("repair"),
            "lease": {key: (lease or {}).get(key) for key in ("_id", "workspace_id", "sender_id", "reservation_job_id")} if lease else None,
            "slot": {key: (slot or {}).get(key) for key in ("_id", "workspace_id", "sender_id", "reservation_job_id")} if slot else None,
            "custody_expires_at": credential_deadline(job)}
        view["verification_requests"] = [{key: record.get(key) for key in ("_id", "owner_token", "status", "mutation", "credential_generation")} for record in physical]
        # Lease/slot collections contain identifiers and reservation metadata only.
        view["review_digest"] = canonical_hash(view)
        return view

    async def verification_receipts(self, job: dict) -> list[dict]:
        return await self.db.outreach_physical_requests.find({"workspace_id": job["workspace_id"], "sender_id": job["sender_id"],
            "source": "verify", "credential_generation": "pending:" + job["id"], "mutation": False,
            "status": {"$in": ["in_flight", "unknown_outcome", "response_received", "resolved"]}}).limit(100).to_list(length=100)

    async def resolve(self, workspace_id: str, job_id: str, decision: str, operator: str, evidence: str,
                      *, workers_drained: bool = False, expected_digest: str) -> dict:
        require_review(operator, evidence, workers_drained)
        if decision not in {"retain_installed", "stop_and_scrub"}:
            raise ValueError("Unsupported connection decision")
        scope = {"workspace_id": workspace_id, "id": job_id}
        job = await self.db.outreach_connection_jobs.find_one(scope)
        if not job:
            raise ValueError("Connection job not found")
        if job.get("repair"):
            if job["repair"]["decision"] != decision:
                if job["status"] != "repairing" or job["repair"]["decision"] != "retain_installed" or decision != "stop_and_scrub":
                    raise ValueError("A different connection decision was already recorded")
                view = await self.inspect(workspace_id, job_id)
                if not expected_digest or view["review_digest"] != expected_digest:
                    raise ValueError("Fresh drained inspection is required to stop an unfinished retain repair")
                await ExecutionPermission(self.db).revoke(workspace_id, job["sender_id"], operator, "connection_repair_stop")
                replacement = {"decision": decision, "operator": operator.strip(), "evidence": evidence.strip(), "workers_drained": True,
                    "review_digest": expected_digest, "at": datetime.now(timezone.utc), "provenance": "operator_inspection"}
                changed = await self.db.outreach_connection_jobs.update_one({**scope, "status": "repairing", "repair": job["repair"]}, {
                    "$set": {"repair": replacement}, "$push": {"repair_history": job["repair"]}})
                if not changed.matched_count:
                    raise ValueError("Saved repair changed")
            return await self.finish(workspace_id, job_id)
        if job["status"] != "finalizing":
            raise ValueError("Connection is not awaiting finalization repair")
        view = await self.inspect(workspace_id, job_id)
        if not expected_digest or view["review_digest"] != expected_digest:
            raise ValueError("Review snapshot changed; inspect it again")
        account = await self.db.outreach_accounts.find_one(self.account_scope(job))
        fence = (account or {}).get("connection_finalization") or {}
        if fence.get("job_id") == job_id:
            expected = fence.get("generation") if fence.get("ever_installed") else fence.get("base_generation")
            if (account or {}).get("credential_generation") != expected:
                raise ValueError("Replacement account generation requires separate review")
        elif account and account.get("credential_generation") != job.get("credential_generation"):
            raise ValueError("Legacy account generation is ambiguous")
        if decision == "retain_installed":
            await self.validate_installed(job)
        await ExecutionPermission(self.db).revoke(workspace_id, job["sender_id"], operator, "connection_repair")
        repair = {"decision": decision, "operator": operator.strip(), "evidence": evidence.strip(), "workers_drained": True,
            "review_digest": expected_digest, "at": datetime.now(timezone.utc), "provenance": "operator_inspection"}
        changed = await self.db.outreach_connection_jobs.update_one({**scope, "status": "finalizing", "repair": {"$exists": False},
            "credential_generation": job.get("credential_generation"), "verification_owner_token": job.get("verification_owner_token")}, {
            "$set": {"status": "repairing", "repair": repair}})
        if not changed.matched_count:
            raise ValueError("Connection changed during review")
        return await self.finish(workspace_id, job_id)

    async def validate_installed(self, job: dict) -> tuple[dict, dict]:
        account = await self.db.outreach_accounts.find_one(self.account_scope(job))
        fence = (account or {}).get("connection_finalization") or {}
        inventory = await self.db.outreach_proxy_inventory.find_one({"_id": job["proxy_id"]})
        if inventory and inventory.get('provider') == 'webshare_plan':
            from outreach.core.webshare_provisioning import managed_webshare_valid
            from outreach.core.proxy_custody import proxy_digest
            if (not await managed_webshare_valid(self.db, inventory, job['workspace_id'])
                    or proxy_digest(inventory) != proxy_digest((account or {}).get('proxy') or {})):
                raise ValueError('Installed Webshare asset needs ownership review')
        lease = await self.db.outreach_proxy_leases.find_one({"_id": job["proxy_id"], "workspace_id": job["workspace_id"], "sender_id": job["sender_id"]})
        slot = await self.db.outreach_sender_slots.find_one({"workspace_id": job["workspace_id"], "sender_id": job["sender_id"]})
        if (not account or account.get("credential_generation") != job.get("credential_generation")
                or account.get("linkedin_urn") != job.get("expected_linkedin_urn") or account.get("is_deleted")
                or account.get("status") != "active" or not account.get("session_cookie_enc")
                or (account.get("proxy") or {}).get("proxy_id") != job["proxy_id"]
                or account.get("country_code") != job["country_code"]
                or not lease or not slot or not inventory or inventory.get("status") != "available"
                or inventory.get("last_workspace_id") != job["workspace_id"] or inventory.get("country_code") != job["country_code"]
                or not _utc(inventory.get("expires_at")) or _utc(inventory["expires_at"]) <= datetime.now(timezone.utc)
                or not await get_active_entitlement(self.db, job["workspace_id"])):
            raise ValueError("Exact installed session, paid term, and bound IP are required; no credentials are restored")
        if fence and (fence.get("job_id") != job["id"] or not fence.get("ever_installed")
                or fence.get("state") not in {"installed", "closed"}
                or fence.get("installed_credential_digest") and fence["installed_credential_digest"] != installed_digest(account)
                or fence.get("state") == "closed" and not (fence.get("repair_decision") == "retain_installed"
                    or fence.get("completion") == "verified_install")):
            raise ValueError("Installed finalization fence is unavailable")
        return account, fence

    async def finish(self, workspace_id: str, job_id: str) -> dict:
        scope = {"workspace_id": workspace_id, "id": job_id}
        job = await self.db.outreach_connection_jobs.find_one(scope)
        if not job or not job.get("repair") or job["status"] not in {"repairing", "repaired_stopped", "completed"}:
            raise ValueError("No saved drained connection repair exists")
        repair = job["repair"]
        await ExecutionPermission(self.db).revoke(workspace_id, job["sender_id"], repair["operator"], "connection_repair")
        if job.get("repair_cleanup_complete"):
            return {"status": job["status"], "job_id": job_id}
        if job["status"] != "repairing":
            # The account/resource stage was already committed. A replacement
            # account after lock deletion must not be revisited on cleanup retry.
            await self.db.outreach_connection_locks.delete_one({"_id": job["sender_id"], "workspace_id": workspace_id, "job_id": job_id})
            await self.db.outreach_connection_jobs.update_one({**scope, "status": job["status"], "repair": repair}, {
                "$set": {"repair_cleanup_complete": True, "created_at": datetime.now(timezone.utc)}})
            return {"status": job["status"], "job_id": job_id}
        for receipt in await self.verification_receipts(job):
            if receipt["status"] in {"in_flight", "unknown_outcome", "resolved"}:
                await ExecutionPermission(self.db).resolve_request(workspace_id, job["sender_id"], receipt["_id"],
                    repair["operator"], "read_interrupted", repair["evidence"], workers_drained=True)
            else:
                from outreach.core.sender_execution import SenderExecution
                await SenderExecution(self.db).release(workspace_id, job["sender_id"], receipt["owner_token"])
        # Leave campaign activation and all future permission grants explicit.
        await self.db.outreach_campaigns.update_many({"workspace_id": workspace_id, "sender_account_ids": job["sender_id"],
            "status": {"$in": ["active", "warming_up"]}}, {"$set": {"status": "paused", "auto_launch_enabled": False},
            "$inc": {"authorization_revision": 1}, "$addToSet": {"pause_reasons": "connection_repair"}})
        account = await self.db.outreach_accounts.find_one(self.account_scope(job))
        fence = (account or {}).get("connection_finalization") or {}
        proven_uninstalled = False
        if repair["decision"] == "retain_installed":
            account, fence = await self.validate_installed(job)
            changed = await self.db.outreach_accounts.update_one({**self.account_scope(job),
                "credential_generation": job["credential_generation"], "connection_finalization": fence if fence else {"$exists": False},
                "status": "active", "linkedin_urn": job["expected_linkedin_urn"], "is_deleted": {"$ne": True},
                "country_code": job["country_code"], "proxy": account.get("proxy"),
                **{key: account[key] if key in account else {"$exists": False} for key in ACCOUNT_SECRETS}}, {
                "$set": {"connection_finalization": {**fence, "job_id": job_id, "state": "closed", "ever_installed": True,
                    "generation": job["credential_generation"], "repair_decision": "retain_installed"}}})
            if not changed.matched_count:
                raise ValueError("Installed account changed during repair")
            status = "completed"
        else:
            if fence.get("job_id") == job_id:
                outcome = await self.close_fence(job)
                proven_uninstalled = outcome["proven_uninstalled"]
            elif account:
                changed = await self.db.outreach_accounts.update_one({**self.account_scope(job),
                    "credential_generation": job.get("credential_generation"), "connection_finalization": {"$exists": False}}, {
                    "$set": {"status": "reauth_required"}, "$unset": ACCOUNT_SECRETS})
                if not changed.matched_count:
                    raise ValueError("Legacy account changed; retain resources")
            # Only this job's newly reserved resources may be released. Any
            # legacy/possibly installed asset remains bound through provider term.
            if proven_uninstalled:
                if job.get("new_proxy_reservation"):
                    await self.db.outreach_proxy_leases.delete_one({"_id": job["proxy_id"], "workspace_id": workspace_id,
                        "sender_id": job["sender_id"], "reservation_job_id": job_id})
                if job.get("created_slot"):
                    await self.db.outreach_sender_slots.delete_one({"workspace_id": workspace_id, "sender_id": job["sender_id"], "reservation_job_id": job_id})
            status = "repaired_stopped"
        resources_retained = bool(await self.db.outreach_proxy_leases.find_one({"workspace_id": workspace_id, "sender_id": job["sender_id"]})
            or await self.db.outreach_sender_slots.find_one({"workspace_id": workspace_id, "sender_id": job["sender_id"]}))
        await self.db.outreach_connection_jobs.update_one({**scope, "status": "repairing", "repair": repair}, {
            "$set": {"status": status, "repair_resources_retained": resources_retained},
            "$unset": {**PENDING_SECRETS, "verification_owner_token": ""}})
        await self.db.outreach_connection_locks.delete_one({"_id": job["sender_id"], "workspace_id": workspace_id, "job_id": job_id})
        await self.db.outreach_connection_jobs.update_one({**scope, "status": status, "repair": repair}, {
            "$set": {"repair_cleanup_complete": True, "created_at": datetime.now(timezone.utc)}})
        return {"status": status, "job_id": job_id}

    async def sweep(self, *, limit: int = 100, now: datetime | None = None) -> dict:
        """Independent of live flags; scrub overdue custody and retry saved repairs."""
        now = now or datetime.now(timezone.utc)
        jobs = await self.db.outreach_connection_jobs.find({"$and": [{"$or": [
            {"status": {"$in": ["finalizing", "repairing"]}},
            {"status": "completed", "connection_cleanup_complete": False},
            {"status": {"$in": ["completed", "repaired_stopped"]}, "repair": {"$exists": True}, "repair_cleanup_complete": {"$ne": True}}]},
            {"$or": [{"next_custody_check_at": {"$exists": False}}, {"next_custody_check_at": {"$lte": now}}]}], "$or": [
            {"custody_expires_at": {"$lte": now}}, {"custody_expires_at": {"$exists": False}},
            {"status": "completed", "connection_cleanup_complete": False},
            {"status": "repairing"}, {"repair": {"$exists": True}, "repair_cleanup_complete": {"$ne": True}}]}).sort([("next_custody_check_at", 1), ("id", 1)]).limit(limit).to_list(length=limit)
        processed = 0
        for job in jobs:
            try:
                if job["status"] == "completed" and job.get("connection_cleanup_complete") is False:
                    await self.db.outreach_connection_locks.delete_one({"_id": job["sender_id"], "workspace_id": job["workspace_id"], "job_id": job["id"]})
                    await self.db.outreach_connection_jobs.update_one({**self.scope(job), "status": "completed", "connection_cleanup_complete": False}, {
                        "$set": {"connection_cleanup_complete": True, "created_at": now}})
                elif job.get("repair") and not job.get("repair_cleanup_complete"):
                    await self.finish(job["workspace_id"], job["id"])
                elif job["status"] == "finalizing" and (not credential_deadline(job) or credential_deadline(job) <= now):
                    await self.expire(job, now=now)
                processed += 1
            except Exception as exc:
                # Quarantine conflicts/outages and rotate the bounded scan.
                # No error strings or pending secrets are copied into logs.
                logger.warning("Connection repair retained (%s)", type(exc).__name__)
            finally:
                await self.db.outreach_connection_jobs.update_one(self.scope(job), {"$set": {"next_custody_check_at": now + timedelta(minutes=1)}})
        return {"processed": processed}
