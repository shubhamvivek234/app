"""Short-lived, explicit operator permission. Feature flags never grant it."""
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from outreach.core.authorization import canonical_hash
from outreach.core.paid_access import _utc

SOURCES = frozenset({"sequence", "sync", "search", "inbox_reply", "engage", "verify", "email_send", "email_find"})
MAX_PERMISSION_SECONDS = 60


class ExecutionPermission:
    def __init__(self, db) -> None:
        self.db = db

    @staticmethod
    def scope(workspace_id: str, sender_id: str) -> dict:
        if not workspace_id or not sender_id:
            raise ValueError("Workspace and sender are required")
        return {"_id": canonical_hash([workspace_id, sender_id]), "workspace_id": workspace_id, "sender_id": sender_id}

    async def grant(self, workspace_id: str, sender_id: str, generation: str, sources: list[str],
                    operator: str, *, ttl_seconds: int = 60, clear_latch: bool = False,
                    now: datetime | None = None) -> dict:
        """Grant and restore stops serialize on the same workspace guard."""
        from outreach.core.erasure import workspace_is_open
        if not await workspace_is_open(self.db, workspace_id):
            raise ValueError("Workspace is closed for erasure")
        from outreach.core import suppression
        async def apply(current):
            return await ExecutionPermission(current)._grant(workspace_id, sender_id, generation,
                sources, operator, ttl_seconds=ttl_seconds, clear_latch=clear_latch, now=now)
        return await suppression.mutate_suppression(self.db, workspace_id, apply)

    async def _grant(self, workspace_id: str, sender_id: str, generation: str, sources: list[str],
                     operator: str, *, ttl_seconds: int = 60, clear_latch: bool = False,
                     now: datetime | None = None) -> dict:
        """Private callback: no provider/key work and no unknown-commit fallback."""
        if (not generation or not operator.strip() or not sources or not set(sources) <= SOURCES
                or type(ttl_seconds) is not int or not 1 <= ttl_seconds <= MAX_PERMISSION_SECONDS):
            raise ValueError("Invalid execution permission")
        from outreach.core.erasure import workspace_is_open
        if not await workspace_is_open(self.db, workspace_id):
            raise ValueError("Workspace is closed for erasure")
        from outreach.core.restore_epoch import positive
        epoch = await positive(self.db, workspace_id)
        now = now or datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)
        if generation.startswith("pending:"):
            from outreach.core.connection_repair import credential_deadline
            job = await self.db.outreach_connection_jobs.find_one({"id": generation[len("pending:"):],
                "workspace_id": workspace_id, "sender_id": sender_id, "status": {"$in": ["queued", "running"]}})
            deadline = credential_deadline(job) if job else None
            if set(sources) != {"verify"} or not deadline or deadline < now + timedelta(seconds=1) or job.get("custody_expired_at"):
                raise ValueError("Pending verification custody expired or job scope is unavailable")
            expires_at = min(expires_at, deadline)
        scope = self.scope(workspace_id, sender_id)
        # A caught duplicate insert still aborts a real Mongo transaction.
        # The shared guard serializes participating creation/grants instead.
        await self.db.outreach_sender_execution.update_one(scope, {'$setOnInsert': {
            'status': 'idle', 'permission_revision': 0}}, upsert=True)
        query = dict(scope)
        query["physical_request_token"] = {"$exists": False}
        if not clear_latch:
            query["permission.latched"] = {"$ne": True}
        # Physical uncertainty is independent of an operator stop. Explicit
        # unlatching alone never authorizes an unresolved possible submission.
        unknown = await self.db.outreach_physical_requests.find_one({
            "workspace_id": workspace_id, "sender_id": sender_id,
            "mutation": True, "status": {"$in": ["in_flight", "unknown_outcome"]},
        })
        if unknown:
            raise ValueError("Unresolved physical submission requires review")
        storage_lock = await self.db.outreach_connection_locks.find_one({"workspace_id": workspace_id, "_id": sender_id})
        if storage_lock and (storage_lock.get("storage_outcome_unknown") or (
                storage_lock.get("storage_protocol") == 1 and not generation.startswith("pending:"))):
            raise ValueError("Unresolved connection storage requires drained operator review")
        finalizing = await self.db.outreach_connection_jobs.find_one({
            "workspace_id": workspace_id, "sender_id": sender_id, "$or": [
                {"status": {"$in": ["finalizing", "repairing"]}},
                {"status": "running", "finalization_prepared": True},
                {"repair": {"$exists": True}, "repair_cleanup_complete": {"$ne": True}}]})
        if finalizing:
            raise ValueError("Unresolved connection finalization requires drained operator repair")
        manual_review = await self.db.outreach_manual_actions.find_one({"workspace_id": workspace_id, "account_id": sender_id,
            "$or": [{"status": {"$in": ["unknown_outcome", "resolving"]}},
                    {"status": "resolved", "cleanup_complete": {"$ne": True}}]})
        if manual_review:
            raise ValueError("Unresolved manual action requires drained stage review")
        permission = {"credential_generation": generation, "sources": sorted(set(sources)),
                      "issued_at": now, "expires_at": expires_at,
                      "operator": operator.strip(), "latched": False, "stop_reason": None}
        await positive(self.db, workspace_id, captured=epoch.captured)
        result = await self.db.outreach_sender_execution.update_one(query, {
            "$set": {"permission": permission}, "$inc": {"permission_revision": 1},
            "$push": {"permission_history": {**permission, "event": "grant"}},
        })
        if getattr(result, "matched_count", 0) != 1:
            raise ValueError("Execution permission is latched; explicit operator release is required")
        doc = await self.db.outreach_sender_execution.find_one(scope)
        permission = doc["permission"]
        await self.db.outreach_execution_permissions.update_one(scope, {"$set": {
            **permission, "revision": doc["permission_revision"]}}, upsert=True)
        if not epoch.live():
            from outreach.core.restore_epoch import EpochUnavailable
            raise EpochUnavailable('Restore configuration changed during grant')
        return {**scope, **permission, "revision": doc["permission_revision"]}

    async def allowed(self, workspace_id: str, sender_id: str, generation: str, source: str,
                      *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if source not in SOURCES or not generation:
            return False
        from outreach.core.restore_epoch import positive, EpochUnavailable
        try:
            epoch = await positive(self.db, workspace_id)
        except EpochUnavailable:
            return False
        if hasattr(type(self.db), 'note_schedule'):
            self.db.checks.append(lambda stamp: epoch.live())
        authority = await self.db.outreach_sender_execution.find_one(self.scope(workspace_id, sender_id))
        doc = (authority or {}).get("permission")
        if not doc or doc.get("latched") or doc.get("credential_generation") != generation or source not in doc.get("sources", []):
            return False
        issued, expiry = _utc(doc.get("issued_at")), _utc(doc.get("expires_at"))
        if doc.get('health_control_id'):
            from outreach.core.health_monitor import controlled_permission_allowed
            if not await controlled_permission_allowed(self.db, authority, doc, now):
                return False
        return bool(epoch.live() and issued and expiry and issued <= now < expiry
                    and 0 < (expiry - issued).total_seconds() <= MAX_PERMISSION_SECONDS)

    async def revoke(self, workspace_id: str, sender_id: str, operator: str, reason: str,
                     *, now: datetime | None = None) -> None:
        if not operator or not reason:
            raise ValueError("Operator and stop reason are required")
        scope = self.scope(workspace_id, sender_id)
        try:
            await self.db.outreach_sender_execution.insert_one({**scope, "status": "idle", "permission_revision": 0})
        except DuplicateKeyError:
            pass
        stopped = {"permission.latched": True, "permission.expires_at": now or datetime.now(timezone.utc),
                   "permission.stop_reason": reason[:120], "permission.stopped_by": operator}
        await self.db.outreach_sender_execution.update_one(scope, {"$set": stopped, "$inc": {"permission_revision": 1},
            "$push": {"permission_history": {"event": "revoke", "operator": operator, "reason": reason[:120], "at": now or datetime.now(timezone.utc)}}})
        # Read-only compatibility projection; never used as execution authority.
        await self.db.outreach_execution_permissions.update_one(scope, {"$set": {
            "latched": True, "expires_at": now or datetime.now(timezone.utc),
            "stop_reason": reason[:120], "stopped_by": operator}}, upsert=True)

    async def resolve_request(self, workspace_id: str, sender_id: str, request_id: str, operator: str,
                              decision: str, evidence: str, *, workers_drained: bool = False,
                              now: datetime | None = None) -> None:
        """Audited assertion after draining; never grants permission or resumes work."""
        if (not workers_drained or not operator.strip() or not 20 <= len(evidence.strip()) <= 2000
                or decision not in {"confirmed_sent", "not_sent_stop", "read_interrupted"}):
            raise ValueError("Drain workers and provide an explicit decision with evidence")
        scope = {"_id": request_id, "workspace_id": workspace_id, "sender_id": sender_id}
        record = await self.db.outreach_physical_requests.find_one(scope)
        if not record or record.get("status") not in {"preparing", "in_flight", "unknown_outcome", "resolved"}:
            raise ValueError("Physical request is not awaiting review")
        if bool(record.get("mutation")) == (decision == "read_interrupted"):
            raise ValueError("Review decision does not match the request kind")
        if record.get("status") == "preparing" and decision == "confirmed_sent":
            raise ValueError("A preparing request has no submission evidence")
        # Stop authority first. A failed later write must never leave a grant
        # usable while the physical token or sender owner has been cleared.
        await self.revoke(workspace_id, sender_id, operator, "physical_review_complete", now=now)
        if record.get("status") == "resolved":
            if (record.get("resolution") or {}).get("decision") != decision:
                raise ValueError("A different decision was already recorded")
        else:
            identity = {key: record.get(key) for key in ("owner_token", "credential_generation", "source", "action", "logical_operation_id", "mutation")}
            changed = await self.db.outreach_physical_requests.update_one({**scope, **identity, "status": record["status"]}, {
                "$set": {"status": "resolved", "original_status": record["status"], "resolution": {
                    "decision": decision, "evidence": evidence.strip(), "operator": operator.strip(),
                    "provenance": "human_assertion", "workers_drained": True,
                    "at": now or datetime.now(timezone.utc)}}})
            if getattr(changed, "matched_count", 0) != 1:
                raise ValueError("Physical request changed during review")
        # Clear only this request's token; keep independent operator permission stopped.
        from outreach.core.sender_execution import SenderExecution
        guard = SenderExecution(self.db)
        await self.db.outreach_sender_execution.update_one({
            **guard.scope(workspace_id, sender_id), "owner_token": record["owner_token"], "physical_request_token": request_id},
            {"$unset": {"physical_request_token": ""}})
        await guard.release(workspace_id, sender_id, record["owner_token"])
