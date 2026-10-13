"""Stop-first, bounded campaign deletion; restoration never grants execution."""
from datetime import datetime, timezone
import uuid
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from fastapi import HTTPException

from outreach.core.authorization import canonical_hash
from outreach.core.suppression import mutate_suppression, SuppressionDatabase

Database = AsyncIOMotorDatabase | SuppressionDatabase
Document = dict[str, Any]
from outreach.core.workspace_scope import workspace_scope

BATCH_SIZE = 200
MAX_STEPS = 20


def operation_id(workspace_id: str, campaign_id: str, request_id: str) -> tuple[str, str]:
    try:
        request_id = str(uuid.UUID(request_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "A valid deletion request UUID is required") from None
    return canonical_hash(["campaign-delete", workspace_id, campaign_id, request_id]), request_id


def _scope(workspace_id: str, campaign_id: str) -> Document:
    return {"id": campaign_id, **workspace_scope(workspace_id)}


def _result(journal: Document) -> Document:
    return {"status": journal["status"], "id": journal["campaign_id"],
            "name": journal.get("name", "Campaign"), "request_id": journal["request_id"]}


async def _start(db: Database, workspace_id: str, campaign_id: str, request_id: str | None) -> Document:
    async def apply(current: SuppressionDatabase) -> Document:
        if request_id is not None:
            identity, _ = operation_id(workspace_id, campaign_id, request_id)
            previous = await current.outreach_campaign_deletions.find_one({"_id": identity, **workspace_scope(workspace_id)})
            if previous:
                return previous
        query = _scope(workspace_id, campaign_id)
        campaign = await current.outreach_campaigns.find_one(query)
        if not campaign:
            raise HTTPException(404, "Campaign not found")
        chosen = request_id
        if chosen is None and campaign.get("is_deleted") is True:
            chosen = campaign.get("deletion_request_id")
        chosen = chosen or str(uuid.uuid4())
        identity, chosen = operation_id(workspace_id, campaign_id, chosen)
        journal_query = {"_id": identity, **workspace_scope(workspace_id)}
        journal = await current.outreach_campaign_deletions.find_one(journal_query)
        if journal:
            return journal
        if campaign.get("is_deleted") is True and campaign.get("deletion_operation_id"):
            raise HTTPException(409, "Another deletion is in progress. Reload its original request.")
        now = datetime.now(timezone.utc)
        journal = {"_id": identity, "workspace_id": workspace_id, "campaign_id": campaign_id,
                   "request_id": chosen, "parent_id": campaign["_id"], "name": campaign.get("name", "Campaign"),
                   "status": "deletion_pending", "phase": 0, "created_at": now,
                   "legacy_partial": campaign.get("is_deleted") is True}
        # Write the parent first in the same transaction as the durable manifest.
        stopped = await current.outreach_campaigns.update_one({**query, "_id": campaign["_id"]}, {"$set": {
            "is_deleted": True, "status": "paused", "auto_launch_enabled": False,
            "deletion_operation_id": identity, "deletion_request_id": chosen,
            "deletion_state": "pending", "updated_at": now},
            "$inc": {"authorization_revision": 1}, "$addToSet": {"pause_reasons": "restore_review"}})
        if stopped.matched_count != 1:
            raise HTTPException(409, "Campaign changed before deletion could stop it")
        await current.outreach_campaign_deletions.insert_one(journal)
        return journal
    return await mutate_suppression(db, workspace_id, apply)


async def _step(db: Database, workspace_id: str, journal: Document, restoring: bool = False) -> Document:
    async def apply(current: SuppressionDatabase) -> Document:
        jq = {"_id": journal["_id"], **workspace_scope(workspace_id)}
        saved = await current.outreach_campaign_deletions.find_one(jq)
        desired = "restore_pending" if restoring else "deletion_pending"
        if saved["status"] != desired:
            return saved
        cq = {**_scope(workspace_id, saved["campaign_id"]), "is_deleted": True,
              "deletion_operation_id": saved["_id"], "_id": saved["parent_id"]}
        parent = await current.outreach_campaigns.find_one(cq)
        if not parent:
            raise HTTPException(409, "Campaign generation changed; this operation cannot continue")
        fenced = await current.outreach_campaigns.update_one(cq, {"$inc": {"deletion_progress_revision": 1}})
        if fenced.matched_count != 1:
            raise HTTPException(409, "Campaign generation changed before cleanup")
        now = datetime.now(timezone.utc)
        phase = saved["phase"]
        row_scope = {"campaign_delete_operation": saved["_id"], **workspace_scope(workspace_id)}
        if restoring:
            if phase == 0:
                # Cancelled tasks stay cancelled. A later explicit launch creates fresh authority.
                collection = current.outreach_tasks
                query = {**row_scope, "campaign_id": saved["campaign_id"]}
            elif phase == 1:
                collection = current.outreach_leads
                query = {**row_scope, "previous_campaign_id": saved["campaign_id"], "campaign_id": None, "pipeline_stage": "unassigned"}
            else:
                collection = current.outreach_sequences
                query = {**row_scope, "campaign_id": saved["campaign_id"], "is_deleted": True}
        else:
            query = {"campaign_id": saved["campaign_id"], **workspace_scope(workspace_id)}
            if phase == 0:
                collection = current.outreach_tasks
                query["status"] = {"$in": ["queued", "pending", "scheduled"]}
            elif phase == 1:
                collection = current.outreach_leads
            else:
                collection = current.outreach_sequences
                query["is_deleted"] = {"$ne": True}
        rows = await collection.find(query).sort("_id", 1).to_list(BATCH_SIZE)
        for row in rows:
            exact = {**query, "_id": row["_id"]}
            if restoring:
                values = {"updated_at": now}
                if phase == 1:
                    values.update(campaign_id=saved["campaign_id"],
                                  pipeline_stage=row.get("deleted_pipeline_stage") or "enrolled")
                elif phase == 2:
                    values["is_deleted"] = False
                await collection.update_one(exact, {"$set": values, "$unset": {
                    "campaign_delete_operation": "", "deleted_pipeline_stage": "",
                    "previous_campaign_id": ""} if phase == 1 else {"campaign_delete_operation": ""}})
            else:
                values = {"updated_at": now, "campaign_delete_operation": saved["_id"]}
                if phase == 0:
                    values.update(status="cancelled", cancelled_due_to_campaign_delete=True)
                elif phase == 1:
                    values.update(pipeline_stage="unassigned", campaign_id=None,
                                  previous_campaign_id=saved["campaign_id"],
                                  deleted_pipeline_stage=row.get("pipeline_stage", "enrolled"))
                else:
                    values["is_deleted"] = True
                await collection.update_one(exact, {"$set": values})
        if rows:
            return saved
        if phase < 2:
            await current.outreach_campaign_deletions.update_one(jq, {"$inc": {"phase": 1}})
            return {**saved, "phase": phase + 1}
        state = "restored" if restoring else "deleted"
        parent_updates = {"deletion_state": state, "updated_at": now}
        if restoring:
            parent_updates.update(is_deleted=False, status="paused", auto_launch_enabled=False,
                leads_count=await current.outreach_leads.count_documents({"campaign_id": saved["campaign_id"],
                    **workspace_scope(workspace_id), "execution_state": {"$ne": "staged"}}))
        await current.outreach_campaigns.update_one(cq, {"$set": parent_updates})
        await current.outreach_campaign_deletions.update_one(jq, {"$set": {"status": state, "completed_at": now}})
        return {**saved, "status": state}
    return await mutate_suppression(db, workspace_id, apply)


async def delete(db: Database, workspace_id: str, campaign_id: str, request_id: str | None = None) -> Document:
    journal = await _start(db, workspace_id, campaign_id, request_id)
    for _ in range(MAX_STEPS):
        if journal["status"] != "deletion_pending":
            break
        journal = await _step(db, workspace_id, journal)
    return _result(journal)


async def restore(db: Database, workspace_id: str, campaign_id: str, request_id: str | None = None) -> Document:
    async def begin(current: SuppressionDatabase) -> Document:
        parent = await current.outreach_campaigns.find_one(_scope(workspace_id, campaign_id))
        if not parent:
            raise HTTPException(404, "Campaign not found")
        chosen = request_id or parent.get("deletion_request_id")
        if not chosen:
            raise HTTPException(409, "This older deletion requires review before restoration")
        identity, _ = operation_id(workspace_id, campaign_id, chosen)
        jq = {"_id": identity, **workspace_scope(workspace_id)}
        journal = await current.outreach_campaign_deletions.find_one(jq)
        if not journal or parent.get("deletion_operation_id") != identity or parent["_id"] != journal["parent_id"]:
            raise HTTPException(409, "Deletion generation changed; reload the campaign")
        if journal["status"] == "restored":
            return journal
        if journal["status"] == "deletion_pending":
            raise HTTPException(409, "Finish deletion before restoring this campaign")
        if journal["status"] == "deleted":
            await current.outreach_campaign_deletions.update_one(jq, {"$set": {"status": "restore_pending", "phase": 0}})
            return {**journal, "status": "restore_pending", "phase": 0}
        return journal
    journal = await mutate_suppression(db, workspace_id, begin)
    for _ in range(MAX_STEPS):
        if journal["status"] != "restore_pending":
            break
        journal = await _step(db, workspace_id, journal, restoring=True)
    return _result(journal)
