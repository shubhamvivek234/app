"""Fence campaign preparation before any lead metadata changes."""
import uuid
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase


async def claim_activation(db: AsyncIOMotorDatabase, campaign: dict, *, sequence_version_id: str | None = None) -> dict | None:
    now = datetime.now(timezone.utc)
    token = str(uuid.uuid4())
    revision = campaign.get("authorization_revision", 0)
    updates = {"launch_claim_token": token, "launch_claim_expires_at": now + timedelta(minutes=5)}
    if sequence_version_id:
        updates["sequence_version_id"] = sequence_version_id
    result = await db.outreach_campaigns.update_one(
        {"id": campaign["id"], "workspace_id": campaign["workspace_id"], "status": campaign["status"],
         "is_deleted": {"$ne": True},
         "authorization_revision": revision if "authorization_revision" in campaign else {"$exists": False},
         "$or": [{"launch_claim_expires_at": None}, {"launch_claim_expires_at": {"$lte": now}}]},
        {"$set": updates,
         "$inc": {"authorization_revision": 1}},
    )
    if getattr(result, "matched_count", 0) == 0:
        return None
    return {"token": token, "revision": revision + 1}


def activation_lead_filter(workspace_id: str, campaign_id: str, revision: int) -> dict:
    return {"workspace_id": workspace_id, "campaign_id": campaign_id,
            "$or": [{"authorized_revision": None}, {"authorized_revision": {"$lte": revision}}]}


async def release_activation(db: AsyncIOMotorDatabase, workspace_id: str, campaign_id: str, token: str) -> bool:
    result = await db.outreach_campaigns.update_one(
        {"id": campaign_id, "workspace_id": workspace_id, "launch_claim_token": token},
        {"$unset": {"launch_claim_token": "", "launch_claim_expires_at": ""}},
    )
    return getattr(result, "matched_count", 0) == 1
