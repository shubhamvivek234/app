"""Durable manual LinkedIn actions; accepted stages repair reporting without resend."""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from celery_workers.shutdown_handler import is_shutting_down
from outreach.core.authorization import canonical_hash
from outreach.core.content_approval import ContentApproval, make_binding
from outreach.core.inbox_freshness import credential_generation
from outreach.core.paid_access import live_actions_enabled, sender_is_ready
from outreach.core.proxy_manager import JITProxyManager
from outreach.core.request_guard import RequestEnvelope, RequestDenied, request_parent, unresolved_physical
from outreach.core.sender_execution import SenderExecution
from outreach.core.safety_shield import SafetyShield
from outreach.engine.voyager_client import VoyagerClient

logger = logging.getLogger(__name__)
ACCEPTED = {"like": "liked", "comment": "commented", "reply": "sent"}


class ManualActions:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    async def target(self, workspace_id: str, target_id: str, source: str) -> dict | None:
        collection = self.db.outreach_engage_posts if source == "engage" else self.db.outreach_inbox_threads
        return await collection.find_one({"id": target_id, "workspace_id": workspace_id})

    async def binding(self, job: dict, account: dict, target: dict) -> dict:
        recipient = target.get("post_urn") if job["source"] == "engage" else target.get("conversation_urn")
        context = {"target_id": job["target_id"], "job_id": job["_id"]}
        if job["source"] == "inbox_reply":
            context["thread_revision"] = target.get("thread_revision", 0)
        return make_binding(workspace_id=job["workspace_id"], account=account, source=job["source"],
            recipient=recipient, action="inbox_reply" if job["action"] == "reply" else job["action"], content=job["content"], context=context)

    async def queue(self, job_id: str, workspace_id: str, account_id: str, target_id: str, source: str, action: str, content: dict, actor: str,
                    *, expected_target: dict | None = None) -> dict:
        if source not in {"engage", "inbox_reply"} or action not in ACCEPTED or not actor:
            raise ValueError("An identified user and supported action are required")
        if (source == "engage") != (action in {"like", "comment"}):
            raise ValueError("Action source does not match")
        account = await self.db.outreach_accounts.find_one({"id": account_id, "workspace_id": workspace_id})
        target = await self.target(workspace_id, target_id, source)
        if not account or not target or (source == "inbox_reply" and target.get("account_id") != account_id):
            raise ValueError("The selected sender or target is unavailable")
        if expected_target is not None and (source != 'inbox_reply' or any(
                target.get(key, 0 if key == 'thread_revision' else None) != expected_target.get(key)
                for key in ('account_id', 'conversation_urn', 'thread_revision'))):
            raise ValueError('The reply recipient or conversation changed')
        now = datetime.now(timezone.utc)
        stages = {name: {"status": "pending"} for name in (["like", "comment"] if action == "comment" and content.get("auto_like") else [action])}
        job = {"_id": job_id, "workspace_id": workspace_id, "account_id": account_id, "target_id": target_id,
               "source": source, "action": action, "content": content, "actor_id": actor,
               "status": "awaiting_approval", "next_due_at": now, "created_at": now, "updated_at": now, "stages": stages}
        job["binding"] = await self.binding(job, account, target)
        prior = await self.db.outreach_manual_actions.find_one({"_id": job_id, "workspace_id": workspace_id})
        if prior:
            if prior["binding"] != job["binding"] or prior["actor_id"] != actor:
                raise ValueError("Another action is pending for this target")
            return prior
        if source == "inbox_reply":
            claimed = await self.db.outreach_inbox_threads.update_one({"id": target_id, "workspace_id": workspace_id,
                "account_id": account_id, "manual_action_id": {"$exists": False},
                "conversation_urn": target.get('conversation_urn'),
                "thread_revision": target["thread_revision"] if "thread_revision" in target else {"$exists": False}}, {
                "$set": {"manual_action_id": job_id}})
            if not claimed.matched_count:
                raise ValueError("A reply is pending or the conversation changed")
        try:
            await self.db.outreach_manual_actions.insert_one(job)
        except DuplicateKeyError:
            prior = await self.db.outreach_manual_actions.find_one({"_id": job_id, "workspace_id": workspace_id})
            if not prior or prior["binding"] != job["binding"]:
                if source == "inbox_reply":
                    await self.db.outreach_inbox_threads.update_one({"id": target_id, "workspace_id": workspace_id, "manual_action_id": job_id}, {
                        "$unset": {"manual_action_id": ""}})
                raise ValueError("Another action is pending for this target") from None
            return prior
        # Insert first: replayed requests must never renew or undo a decision.
        approval = await ContentApproval(self.db).ensure(job["binding"])
        await ContentApproval(self.db).decide(workspace_id, approval["_id"], actor, "approve", revision=approval["revision"])
        await self.db.outreach_manual_actions.update_one({"_id": job_id, "workspace_id": workspace_id, "status": "awaiting_approval"}, {
            "$set": {"status": "queued"}})
        job["status"] = "queued"
        return job

    async def client(self, job: dict, account: dict) -> VoyagerClient:
        from outreach.core.proxy_custody import prepare_proxy
        prepared = await prepare_proxy(account.get("proxy") or account.get("proxy_config") or {}, job["workspace_id"])
        proxy_url = prepared.url
        envelope = RequestEnvelope(self.db, job["workspace_id"], account["id"], credential_generation(account), job["source"], proxy_url,
            prepared_proxy=prepared, operation_id="engage:" + job["target_id"] if job["source"] == "engage" else job["_id"], approval_binding=job["binding"])
        from outreach.core.session_custody import account_session
        return VoyagerClient(**(await account_session(account)), proxy_url=proxy_url, request_envelope=envelope)

    async def validate(self, job: dict, owner: str) -> str | None:
        current = await self.db.outreach_manual_actions.find_one({"_id": job["_id"], "workspace_id": job["workspace_id"], "owner": owner,
            "status": {"$in": ["preparing", "in_flight"]}})
        account = await self.db.outreach_accounts.find_one({"id": job["account_id"], "workspace_id": job["workspace_id"], "status": "active", "is_deleted": {"$ne": True}})
        target = await self.target(job["workspace_id"], job["target_id"], job["source"])
        if not current or current.get("binding") != job["binding"] or current.get("content") != job["content"] or not account or not target:
            return "manual_context_changed"
        if job["source"] == "engage" and (target.get("action_id") != job["_id"] or target.get("status") not in {"pending", "liked"}):
            return "manual_context_changed"
        if job["source"] == "inbox_reply" and (target.get("account_id") != job["account_id"] or target.get("is_demo")):
            return "manual_context_changed"
        if await self.binding(job, account, target) != job["binding"]:
            return "content_changed"
        if not await sender_is_ready(self.db, job["workspace_id"], account):
            return "paid_access_required"
        if not await ContentApproval(self.db).allowed(job["binding"]):
            return "content_approval_required"
        return None

    def physical_id(self, job: dict, stage: str) -> str:
        path = {"like": "/voyager/api/feed/reactions", "comment": "/voyager/api/feed/comments",
                "reply": "/voyager/api/messaging/conversations/" + job["binding"]["recipient"] + "/events"}[stage]
        operation = "engage:" + job["target_id"] if job["source"] == "engage" else job["_id"]
        return canonical_hash([job["workspace_id"], job["account_id"], job["source"], operation, "POST", path, "message" if stage == "reply" else stage])

    async def run(self, workspace_id: str, job_id: str) -> dict:
        if is_shutting_down() or not live_actions_enabled():
            return {"status": "disabled"}
        now = datetime.now(timezone.utc)
        owner = str(uuid.uuid4())
        scope = {"_id": job_id, "workspace_id": workspace_id}
        claimed = await self.db.outreach_manual_actions.update_one({**scope, "next_due_at": {"$lte": now}, "$or": [
            {"status": "queued"}, {"status": "preparing", "claim_expires_at": {"$lte": now}},
        ]}, {"$set": {"status": "preparing", "owner": owner, "claim_expires_at": now + timedelta(minutes=2), "updated_at": now}})
        if not claimed.modified_count:
            return {"status": "already_claimed"}
        job = await self.db.outreach_manual_actions.find_one({**scope, "owner": owner})
        owned = {**scope, "owner": owner}
        guard = SenderExecution(self.db)
        acquired = False
        try:
            reason = await self.validate(job, owner)
            if reason:
                raise RequestDenied(reason)
            if not await guard.acquire(workspace_id, job["account_id"], owner):
                raise RequestDenied("sender_busy", 5)
            acquired = True
            if not await guard.begin(workspace_id, job["account_id"], owner):
                raise RequestDenied("sender_busy", 5)
            account = await self.db.outreach_accounts.find_one({"id": job["account_id"], "workspace_id": workspace_id})
            client = await self.client(job, account)
            if getattr(client, "is_mock", False):
                raise RequestDenied("mock_sender_unavailable")
            for stage, evidence in job["stages"].items():
                if evidence["status"] == "provider_accepted":
                    continue
                if evidence["status"] != "pending":
                    raise RuntimeError("Unresolved stage cannot retry")
                reason = await self.validate(job, owner)
                if reason:
                    raise RequestDenied(reason)
                marked = await self.db.outreach_manual_actions.update_one({**owned, f"stages.{stage}.status": "pending"}, {"$set": {
                    "status": "in_flight", f"stages.{stage}": {"status": "possible_submission", "request_id": self.physical_id(job, stage),
                    "owner_token": owner, "possible_submission_at": datetime.now(timezone.utc)}}})
                if not marked.modified_count:
                    raise RuntimeError("Manual stage owner changed")
                async def validate_request():
                    return await self.validate(job, owner)
                with request_parent(owner, validate_request, approval_binding=job["binding"],
                        transaction_validator=lambda current: ManualActions(current).validate(job, owner)) as parent:
                    try:
                        if stage == "like":
                            result = await client.like_update(job["binding"]["recipient"])
                        elif stage == "comment":
                            result = await client.comment_on_update(job["binding"]["recipient"], job["content"]["body"])
                        else:
                            result = await client.send_conversation_reply(job["binding"]["recipient"], job["content"]["body"])
                    except RequestDenied:
                        if parent.mutation_attempted:
                            raise RuntimeError("Manual stage outcome requires review") from None
                        reset = await self.db.outreach_manual_actions.update_one({**owned, f"stages.{stage}.status": "possible_submission"}, {"$set": {f"stages.{stage}.status": "pending"}})
                        if not reset.matched_count:
                            raise RuntimeError("Manual non-call evidence changed") from None
                        raise
                if result.get("status") != ACCEPTED[stage]:
                    code = result.get("status_code")
                    if code and SafetyShield.should_trip_circuit_breaker(code):
                        await SafetyShield.trip_circuit_breaker(job["account_id"], "Manual LinkedIn action restricted", self.db, workspace_id)
                    raise RuntimeError("Manual stage outcome requires review")
                saved = await self.db.outreach_manual_actions.update_one({**owned, f"stages.{stage}.status": "possible_submission"}, {"$set": {
                    f"stages.{stage}.status": "provider_accepted", f"stages.{stage}.accepted_at": datetime.now(timezone.utc),
                    f"stages.{stage}.provenance": "adapter_response"}})
                if not saved.modified_count:
                    raise RuntimeError("Manual acceptance evidence changed")
            await self.db.outreach_manual_actions.update_one(owned, {"$set": {"status": "projection_pending"}})
            return await self.recover(workspace_id, job_id, owner=owner)
        except RequestDenied as exc:
            await self.db.outreach_manual_actions.update_one({**owned, "status": {"$in": ["preparing", "in_flight"]}}, {"$set": {
                "status": "queued", "defer_reason": exc.reason, "next_due_at": datetime.now(timezone.utc) + timedelta(seconds=exc.retry_after)},
                "$unset": {"owner": "", "claim_expires_at": ""}})
            return {"status": "queued", "reason": exc.reason}
        except Exception as exc:
            logger.error("Manual action interrupted (%s)", type(exc).__name__)
            await self.db.outreach_manual_actions.update_one({**owned, "status": {"$in": ["preparing", "in_flight"]}}, {"$set": {"status": "unknown_outcome"}})
            return {"status": "unknown_outcome"}
        finally:
            if acquired and not await unresolved_physical(self.db, workspace_id, job["account_id"], owner):
                await guard.release(workspace_id, job["account_id"], owner)

    async def project(self, job: dict) -> None:
        ws, target_id = job["workspace_id"], job["target_id"]
        if job["source"] == "engage":
            for stage, evidence in job["stages"].items():
                if evidence["status"] != "provider_accepted":
                    continue
                prefix = "liked" if stage == "like" else "commented"
                updates = {"status": ACCEPTED[stage], prefix + "_at": evidence["accepted_at"], prefix + "_by_account_id": job["account_id"], prefix + "_by_action_id": job["_id"]}
                if stage == "comment":
                    updates["user_comment"] = job["content"]["body"]
                await self.db.outreach_engage_posts.update_one({"id": target_id, "workspace_id": ws, "action_id": job["_id"],
                    prefix + "_by_action_id": {"$ne": job["_id"]}}, {"$set": updates, "$inc": {"reactions_count" if stage == "like" else "comments_count": 1}})
            target = await self.target(ws, target_id, job["source"])
            if target:
                pending = await self.db.outreach_engage_posts.count_documents({"workspace_id": ws, "list_id": target["list_id"], "status": "pending"})
                await self.db.outreach_engage_lists.update_one({"id": target["list_id"], "workspace_id": ws}, {"$set": {"pending_posts_count": pending}})
        else:
            evidence = job["stages"]["reply"]
            if evidence["status"] != "provider_accepted":
                return
            message = {"id": job["_id"], "sender_type": "user", "sender_name": "You", "body": job["content"]["body"],
                       "timestamp": evidence["accepted_at"], "evidence_source": evidence["provenance"]}
            query = {"id": target_id, "workspace_id": ws, "account_id": job["account_id"], "messages.id": {"$ne": job["_id"]}}
            updated = await self.db.outreach_inbox_threads.update_one({**query, "$or": [
                {"last_message_at": {"$lte": evidence["accepted_at"]}}, {"last_message_at": {"$exists": False}}]}, {
                "$push": {"messages": message}, "$inc": {"thread_revision": 1}, "$set": {
                    "last_message_snippet": message["body"][:120], "last_message_at": evidence["accepted_at"]}})
            if not updated.matched_count:
                await self.db.outreach_inbox_threads.update_one(query, {"$push": {"messages": message}, "$inc": {"thread_revision": 1}})
            await self.db.outreach_inbox_jobs.update_one({"id": job["_id"], "workspace_id": ws}, {"$set": {"status": "completed", "result": {"message": message}}})

    async def recover(self, workspace_id: str, job_id: str, *, owner: str | None = None) -> dict:
        scope = {"_id": job_id, "workspace_id": workspace_id}
        job = await self.db.outreach_manual_actions.find_one(scope)
        if not job:
            return {"status": "missing"}
        if job["status"] in {"resolving", "resolved"}:
            from outreach.core.manual_resolution import ManualResolution
            return await ManualResolution(self.db).finish(workspace_id, job_id)
        if job["status"] in {"completed", "cancelled"}:
            if job["status"] == "cancelled":
                await self.project(job)
            await self.cleanup(job)
            return {"status": job["status"]}
        if job["status"] not in {"in_flight", "unknown_outcome", "projection_pending"}:
            return {"status": job["status"]}
        now = datetime.now(timezone.utc)
        if job["status"] == "in_flight" and owner != job.get("owner") and job.get("claim_expires_at", now) > now:
            return {"status": "busy"}
        fence = {**scope, "status": job["status"], "owner": job.get("owner")}
        for stage, evidence in job["stages"].items():
            if evidence["status"] == "possible_submission":
                physical = await self.db.outreach_physical_requests.find_one({"_id": evidence["request_id"], "workspace_id": workspace_id,
                    "sender_id": job["account_id"], "owner_token": evidence.get("owner_token") or job.get("owner"),
                    "credential_generation": job["binding"]["credential_generation"], "source": job["source"],
                    "action": "message" if stage == "reply" else stage, "mutation": True,
                    "logical_operation_id": "engage:" + job["target_id"] if job["source"] == "engage" else job["_id"]})
                if physical and physical.get("status") == "response_received" and physical.get("http_status") in {200, 201}:
                    replacement = {**evidence, "status": "provider_accepted", "accepted_at": physical["completed_at"], "provenance": "transport_response_recovery"}
                    changed = await self.db.outreach_manual_actions.update_one({**fence, f"stages.{stage}.status": "possible_submission"}, {"$set": {f"stages.{stage}": replacement}})
                    if not changed.matched_count:
                        return {"status": "changed"}
                    evidence.update(replacement)
                else:
                    await self.db.outreach_manual_actions.update_one(fence, {"$set": {"status": "unknown_outcome"}})
                    return {"status": "unknown_outcome"}
        if any(stage["status"] != "provider_accepted" for stage in job["stages"].values()):
            # Only pending (proven unattempted) stages remain after receipt repair.
            if all(stage["status"] in {"pending", "provider_accepted"} for stage in job["stages"].values()):
                changed = await self.db.outreach_manual_actions.update_one(fence, {"$set": {"status": "queued", "next_due_at": now},
                    "$unset": {"owner": "", "claim_expires_at": ""}})
                if changed.matched_count:
                    await self.release_owner(job)
                return {"status": "queued" if changed.matched_count else "changed"}
            await self.db.outreach_manual_actions.update_one(fence, {"$set": {"status": "unknown_outcome"}})
            return {"status": "unknown_outcome"}
        try:
            await self.project(job)
            changed = await self.db.outreach_manual_actions.update_one(fence, {"$set": {"status": "completed", "completed_at": now}})
            if not changed.matched_count:
                return {"status": "changed"}
            await self.cleanup(job)
            return {"status": "completed"}
        except Exception as exc:
            logger.warning("Manual action projection pending (%s)", type(exc).__name__)
            await self.db.outreach_manual_actions.update_one(fence, {"$set": {"status": "projection_pending"}})
            return {"status": "projection_pending"}

    async def release_owner(self, job: dict) -> None:
        owner = job.get("owner")
        if owner and not await unresolved_physical(self.db, job["workspace_id"], job["account_id"], owner):
            # Only received/non-submitted receipts belonging to this owner may
            # clear its transport latch. A newer owner is never touched.
            for stage in job["stages"].values():
                request_id = stage.get("request_id")
                if not request_id:
                    continue
                receipt = await self.db.outreach_physical_requests.find_one({"_id": request_id, "workspace_id": job["workspace_id"],
                    "sender_id": job["account_id"], "owner_token": owner, "status": {"$in": ["response_received", "not_submitted"]}})
                if receipt:
                    await self.db.outreach_sender_execution.update_one({**SenderExecution.scope(job["workspace_id"], job["account_id"]),
                        "owner_token": owner, "physical_request_token": request_id}, {"$unset": {"physical_request_token": ""}})
            await self.db.outreach_sender_execution.update_one({**SenderExecution.scope(job["workspace_id"], job["account_id"]),
                "owner_token": owner, "physical_request_token": {"$exists": False}}, {
                "$set": {"status": "idle"}, "$unset": {"owner_token": "", "expires_at": ""}})

    async def cleanup(self, job: dict) -> None:
        await self.release_owner(job)
        if job["source"] == "engage":
            await self.db.outreach_engage_posts.update_one({"id": job["target_id"], "workspace_id": job["workspace_id"], "action_id": job["_id"]}, {
                "$unset": {"action_id": "", "action_queued_at": "", "action_claimed_at": ""}, "$set": {"action_error": ""}})
        else:
            await self.db.outreach_inbox_threads.update_one({"id": job["target_id"], "workspace_id": job["workspace_id"], "manual_action_id": job["_id"]}, {
                "$unset": {"manual_action_id": ""}})
            if job["status"] == "cancelled":
                await self.db.outreach_inbox_jobs.update_one({"id": job["_id"], "workspace_id": job["workspace_id"]}, {"$set": {"status": "cancelled"}})
        await self.db.outreach_manual_actions.update_one({"_id": job["_id"], "workspace_id": job["workspace_id"], "status": {"$in": ["completed", "cancelled", "resolved"]}}, {
            "$set": {"cleanup_complete": True}})

    async def cancel(self, workspace_id: str, job_id: str) -> None:
        scope = {"_id": job_id, "workspace_id": workspace_id}
        job = await self.db.outreach_manual_actions.find_one(scope)
        if not job or job["status"] not in {"queued", "awaiting_approval"} or any(
                stage["status"] not in {"pending", "provider_accepted"} for stage in job["stages"].values()):
            raise ValueError("An active or uncertain action must be reconciled before cancellation")
        changed = await self.db.outreach_manual_actions.update_one({**scope, "status": job["status"]}, {
            "$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc)}})
        if not changed.matched_count:
            raise ValueError("Action changed; refresh before cancelling")
        await self.recover(workspace_id, job_id)
        await self.db.outreach_inbox_jobs.update_one({"id": job_id, "workspace_id": workspace_id}, {"$set": {"status": "cancelled"}})
