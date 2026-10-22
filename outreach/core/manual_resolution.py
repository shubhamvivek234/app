"""Drained manual-action review. Human assertions are never provider receipts."""
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, timezone

from outreach.core.authorization import canonical_hash
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.manual_actions import ManualActions
from outreach.core.paid_access import _utc

DECISIONS = {"confirmed_sent", "not_sent_stop", "use_receipt"}


def require_review(operator: str, evidence: str, workers_drained: bool) -> None:
    if not workers_drained or not operator.strip() or not 20 <= len(evidence.strip()) <= 2000:
        raise ValueError("Drain sender workers and provide an identified operator with 20–2000 characters of evidence")


class ManualResolution:
    def __init__(self, db) -> None:
        self.db = db
        self.actions = ManualActions(db)

    def physical_scope(self, job: dict, stage: str, evidence: dict) -> dict:
        return {"_id": self.actions.physical_id(job, stage), "workspace_id": job["workspace_id"],
            "sender_id": job["account_id"], "owner_token": evidence.get("owner_token") or job.get("owner"),
            "credential_generation": job["binding"]["credential_generation"], "source": job["source"],
            "action": "message" if stage == "reply" else stage, "mutation": True,
            "logical_operation_id": "engage:" + job["target_id"] if job["source"] == "engage" else job["_id"]}

    async def receipt(self, job: dict, stage: str, evidence: dict) -> dict | None:
        scope = self.physical_scope(job, stage, evidence)
        if evidence.get("request_id") != scope["_id"]:
            raise ValueError("Stage request identity differs from the original action")
        raw = await self.db.outreach_physical_requests.find_one({"_id": scope["_id"]})
        if raw and any(raw.get(key) != value for key, value in scope.items()):
            raise ValueError("Physical request ownership or binding changed")
        return raw

    async def inspect(self, workspace_id: str, job_id: str) -> dict:
        job = await self.db.outreach_manual_actions.find_one({"_id": job_id, "workspace_id": workspace_id})
        if not job:
            raise ValueError("Manual action not found")
        stages = {}
        for stage, evidence in job["stages"].items():
            physical = await self.receipt(job, stage, evidence) if evidence.get("request_id") else None
            stages[stage] = {"stage": evidence, "physical": {key: physical.get(key) for key in (
                "_id", "owner_token", "status", "http_status", "completed_at", "resolution")} if physical else None}
        view = {"job_id": job_id, "workspace_id": workspace_id, "sender_id": job["account_id"],
            "status": job["status"], "binding": job["binding"], "owner": job.get("owner"), "stages": stages}
        view["review_digest"] = canonical_hash(view)
        return view

    async def resolve(self, workspace_id: str, job_id: str, decisions: dict[str, str], operator: str,
                      evidence: str, *, workers_drained: bool = False, expected_digest: str) -> dict:
        require_review(operator, evidence, workers_drained)
        scope = {"_id": job_id, "workspace_id": workspace_id}
        job = await self.db.outreach_manual_actions.find_one(scope)
        if not job:
            raise ValueError("Manual action not found")
        if job.get("review"):
            if job["review"]["decisions"] != decisions:
                raise ValueError("A different review decision was already recorded")
            return await self.finish(workspace_id, job_id)
        if job["status"] not in {"unknown_outcome", "in_flight", "projection_pending"}:
            raise ValueError("Manual action is not awaiting review")
        expiry = _utc(job.get("claim_expires_at"))
        if job["status"] == "in_flight" and expiry and expiry > datetime.now(timezone.utc):
            raise ValueError("The original worker claim has not expired")
        view = await self.inspect(workspace_id, job_id)
        if not expected_digest or view["review_digest"] != expected_digest:
            raise ValueError("Review snapshot changed; inspect it again")
        uncertain = {stage for stage, entry in job["stages"].items() if entry["status"] == "possible_submission"}
        if set(decisions) != uncertain or not set(decisions.values()) <= DECISIONS:
            raise ValueError("Provide exactly one supported decision for each uncertain stage")
        for stage in uncertain:
            physical = await self.receipt(job, stage, job["stages"][stage])
            accepted = bool(physical and physical.get("status") == "response_received"
                and physical.get("http_status") in {200, 201} and _utc(physical.get("completed_at")))
            if accepted != (decisions[stage] == "use_receipt"):
                raise ValueError("Use a matching received acceptance receipt; human review cannot contradict it")
            if physical and physical["status"] not in {"preparing", "in_flight", "unknown_outcome", "resolved", "response_received", "not_submitted"}:
                raise ValueError("Physical evidence is not reviewable")
            if physical and physical["status"] == "resolved" and physical["resolution"]["decision"] != decisions[stage]:
                raise ValueError("Physical review decision conflicts")
            if physical and physical["status"] in {"preparing", "not_submitted"} and decisions[stage] != "not_sent_stop":
                raise ValueError("Preparing or proven non-call evidence cannot be marked sent")
        await ExecutionPermission(self.db).revoke(workspace_id, job["account_id"], operator, "manual_review")
        review = {"operator": operator.strip(), "evidence": evidence.strip(), "workers_drained": True,
            "decisions": decisions, "review_digest": expected_digest, "provenance": "human_assertion",
            "at": datetime.now(timezone.utc)}
        changed = await self.db.outreach_manual_actions.update_one({**scope, "status": job["status"],
            "owner": job.get("owner"), "binding": job["binding"], "stages": job["stages"], "review": {"$exists": False}}, {
            "$set": {"status": "resolving", "review": review}})
        if not changed.matched_count:
            raise ValueError("Manual action changed during review")
        return await self.finish(workspace_id, job_id)

    async def finish(self, workspace_id: str, job_id: str) -> dict:
        """Replay saved database repairs only. This method performs no HTTP calls."""
        scope = {"_id": job_id, "workspace_id": workspace_id}
        job = await self.db.outreach_manual_actions.find_one(scope)
        if not job or job["status"] not in {"resolving", "resolved"} or not job.get("review"):
            raise ValueError("No saved drained review exists")
        review = job["review"]
        await ExecutionPermission(self.db).revoke(workspace_id, job["account_id"], review["operator"], "manual_review")
        fence = {**scope, "status": job["status"], "review": review}
        for stage, entry in job["stages"].items():
            if entry["status"] == "pending":
                await self.db.outreach_manual_actions.update_one({**fence, f"stages.{stage}.status": "pending"}, {
                    "$set": {f"stages.{stage}.status": "cancelled"}})
            if entry["status"] != "possible_submission":
                continue
            decision = review["decisions"][stage]
            physical = await self.receipt(job, stage, entry)
            if decision == "use_receipt":
                if not physical or physical["status"] != "response_received" or physical.get("http_status") not in {200, 201}:
                    raise ValueError("Original received acceptance is unavailable")
                replacement = {"status": "provider_accepted", "accepted_at": physical["completed_at"],
                    "provenance": "transport_response_recovery"}
            else:
                if physical and physical["status"] in {"preparing", "in_flight", "unknown_outcome", "resolved"}:
                    await ExecutionPermission(self.db).resolve_request(workspace_id, job["account_id"], physical["_id"],
                        review["operator"], decision, review["evidence"], workers_drained=True)
                elif physical and physical["status"] == "response_received" and physical.get("http_status") in {200, 201}:
                    raise ValueError("Received acceptance changed; review remains held")
                replacement = {"status": "human_confirmed" if decision == "confirmed_sent" else "not_sent_stopped",
                    "provenance": "human_assertion", "reviewed_at": review["at"]}
                # The stage marker itself may predate any physical insert. After
                # draining, clear only its original owner's exact token.
                from outreach.core.sender_execution import SenderExecution
                await self.db.outreach_sender_execution.update_one({**SenderExecution.scope(workspace_id, job["account_id"]),
                    "owner_token": entry.get("owner_token") or job.get("owner"), "physical_request_token": entry["request_id"]},
                    {"$unset": {"physical_request_token": ""}})
            changed = await self.db.outreach_manual_actions.update_one({**fence, f"stages.{stage}": entry}, {
                "$set": {**{f"stages.{stage}.{key}": value for key, value in replacement.items()}}})
            if not changed.matched_count:
                raise ValueError("Manual stage changed during repair")
        job = await self.db.outreach_manual_actions.find_one(scope)
        await self.actions.project(job)  # Only original/received provider acceptances count.
        collection = self.db.outreach_engage_posts if job["source"] == "engage" else self.db.outreach_inbox_threads
        target_scope = {"id": job["target_id"], "workspace_id": workspace_id,
            "action_id" if job["source"] == "engage" else "manual_action_id": job_id}
        if review["decisions"]:
            await collection.update_one(target_scope, {"$set": {"manual_review": {**review,
                "job_id": job_id, "decision": review["decisions"].get(job["action"]), "recorded_only": True}}})
        await self.db.outreach_manual_actions.update_one(fence, {"$set": {"status": "resolved", "resolved_at": review["at"]}})
        job["status"] = "resolved"
        if job["source"] == "inbox_reply" and job["stages"]["reply"]["status"] != "provider_accepted":
            await self.db.outreach_inbox_jobs.update_one({"id": job_id, "workspace_id": workspace_id}, {
                "$set": {"status": "reviewed", "manual_review": review}})
        await self.actions.cleanup(job)
        return {"status": "resolved", "job_id": job_id}
