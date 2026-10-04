"""Recover reporting projections from durable intent evidence without resending."""
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.core.execution_outbox import ExecutionOutbox


async def _recover_provider_receipt(db, intent: dict, now: datetime) -> dict:
    """Promote only this logical attempt's durable, original-owner receipt."""
    source = {"send_email": "email_send", "find_email": "email_find"}.get(intent.get("action_kind"))
    if not source or intent.get("status") != "unknown_outcome" or intent.get("resolution"):
        return intent
    from outreach.core.provider_operations import ProviderOperations
    collection, prefix = ("outreach_email_operations", "email") if source == "email_send" else ("outreach_email_discoveries", "finder")
    ops = ProviderOperations(db, collection)
    operation = await ops.collection.find_one({"workspace_id": intent["workspace_id"],
        "_id": f"{prefix}:{intent['workspace_id']}:{intent['legacy_operation_id']}", "source": source,
        "sender_account_id": intent["sender_id"], "lead_id": intent["lead_id"], "owner_token": intent.get("claim_token"),
        "account_generation": intent["credential_generation"], "lead_snapshot.current_node_id": intent["node_id"],
        "lead_snapshot.authorized_revision": intent["authorization_revision"], "lead_snapshot.sequence_version": intent["sequence_version"]})
    if not operation:
        return intent
    outcome = await ops.received(operation)
    if not outcome or outcome["status"] not in {"accepted", "found", "not_found"}:
        return intent
    if operation["status"] in {"dispatching", "uncertain"} and not await ops.repair(operation):
        return intent
    if source == "email_find" and outcome["status"] == "found":
        from outreach.core.email_finder import _project_discovery
        await _project_discovery(db, operation, outcome, recovering=True)
    changed = await db.outreach_intents.update_one({"_id": intent["_id"], "workspace_id": intent["workspace_id"],
        "status": "unknown_outcome", "claim_token": intent.get("claim_token"), "resolution": {"$exists": False}}, {
        "$set": {"status": "executed", "attempt.outcome": "provider_accepted" if source == "email_send" else "request_observed",
            "attempt.provider_result_status": outcome["status"], "attempt.provider_message_id": outcome.get("provider_message_id"),
            "attempt.provider_thread_id": outcome.get("provider_thread_id"), "recovered_from_physical_receipt": True, "updated_at": now}})
    return await db.outreach_intents.find_one({"_id": intent["_id"], "workspace_id": intent["workspace_id"]}) if changed.matched_count else intent


async def recover_intent(db: AsyncIOMotorDatabase, intent: dict, *, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    workspace_id, intent_id = intent["workspace_id"], intent["_id"]
    if intent.get("status") == "in_flight":
        if not await ExecutionOutbox(db).quarantine_expired(workspace_id, intent_id, now=now):
            return "busy"
        intent = await db.outreach_intents.find_one({"_id": intent_id, "workspace_id": workspace_id})
    intent = await _recover_provider_receipt(db, intent, now)
    scope = {"id": intent["legacy_operation_id"], "workspace_id": workspace_id, "intent_id": intent_id}
    task = await db.outreach_tasks.find_one(scope)
    if not task:
        return "projection_missing"
    if intent.get("status") == "executed":
        attempt = intent.get("attempt") or {}
        if attempt.get("outcome") not in {"provider_accepted", "request_observed"}:
            return "human_review"
        final_status = "accepted" if intent["action_kind"] == "send_email" else (
            "skipped" if attempt.get("provider_result_status") == "skipped" else "completed")
        if task.get("status") in {"preparing", "dispatching", "uncertain"}:
            changed = await db.outreach_tasks.update_one(
                {**scope, "owner_token": intent.get("claim_token"), "status": {"$in": ["preparing", "dispatching", "uncertain"]}},
                {"$set": {"status": final_status, "provider_message_id": attempt.get("provider_message_id"),
                          "provider_thread_id": attempt.get("provider_thread_id"), "updated_at": now}},
            )
            if not changed.matched_count:
                return "busy"
        elif task.get("status") not in {"completed", "accepted", "skipped"}:
            return "human_review"
        await db.outreach_leads.update_one(
            {"id": intent["lead_id"], "workspace_id": workspace_id, "campaign_id": intent["campaign_id"],
             "current_node_id": intent["node_id"], "authorized_revision": intent["authorization_revision"],
             "execution_state": "waiting_trigger", "has_replied": {"$ne": True}},
            {"$set": {"execution_state": "queued", "next_action_due_at": now}},
        )
        from outreach.core.sender_execution import SenderExecution
        owner = intent.get("claim_token")
        sender = await db.outreach_sender_execution.find_one({**SenderExecution.scope(workspace_id, intent["sender_id"]), "owner_token": owner})
        if sender and not await SenderExecution(db).release(workspace_id, intent["sender_id"], owner):
            return "busy"
        await db.outreach_intents.update_one({"_id": intent_id, "workspace_id": workspace_id, "status": "executed",
            "claim_token": owner}, {"$set": {"projection_reconciled": True}})
        return "repaired"
    if intent.get("status") == "unknown_outcome":
        current = await db.outreach_intents.find_one({"_id": intent_id, "workspace_id": workspace_id,
                                                     "status": "unknown_outcome", "resolution": {"$exists": False}})
        if not current:
            return "unchanged"
        # Keep the campaign stopped even if a crash interrupted its pause.
        from outreach.tasks.sequence_executor import _pause_uncertain
        lead = await db.outreach_leads.find_one({"id": intent["lead_id"], "workspace_id": workspace_id,
                                                "campaign_id": intent["campaign_id"]})
        if lead:
            await _pause_uncertain(db, lead, intent["legacy_operation_id"], "An interrupted submission needs outcome review.",
                                   expected_revision=intent["authorization_revision"], expected_node_id=intent["node_id"])
        await db.outreach_intents.update_one({"_id": intent_id, "workspace_id": workspace_id, "status": "unknown_outcome"},
                                            {"$set": {"projection_reconciled": True}})
        return "quarantined"
    return "unchanged"
