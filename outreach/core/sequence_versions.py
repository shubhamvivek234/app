"""Immutable sequence data published through a conditional campaign pointer.

The legacy sequence collection is a compatibility projection. A crash before
pointer publication exposes no new version; a projection failure after it
cannot lose or lock an authoritative saved sequence.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)


async def load_sequence(db: AsyncIOMotorDatabase, workspace_id: str, campaign_id: str, *, campaign: dict | None = None) -> dict | None:
    campaign = campaign if campaign is not None else await db.outreach_campaigns.find_one({
        "id": campaign_id, "workspace_id": workspace_id,
    })
    pointer = campaign.get("sequence_version_id") if isinstance(campaign, dict) else None
    if pointer:
        return await db.outreach_sequence_versions.find_one({
            "_id": pointer, "workspace_id": workspace_id, "campaign_id": campaign_id,
        })
    return await db.outreach_sequences.find_one({
        "campaign_id": campaign_id, "workspace_id": workspace_id, "is_deleted": {"$ne": True},
    })


async def publish_sequence(db: AsyncIOMotorDatabase, workspace_id: str, campaign_id: str, doc: dict, *, expected_revision: int) -> bool:
    campaign = await db.outreach_campaigns.find_one({"id": campaign_id, "workspace_id": workspace_id})
    if not isinstance(campaign, dict) or campaign.get("status") not in {"draft", "paused"} or campaign.get("is_deleted"):
        return False
    revision = campaign.get("authorization_revision", 0)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0 or revision != expected_revision:
        return False
    current = await load_sequence(db, workspace_id, campaign_id, campaign=campaign)
    current_version = current.get("version", 0) if isinstance(current, dict) else 0
    if not isinstance(current_version, int) or isinstance(current_version, bool) or current_version < 0:
        return False
    pointer = str(uuid.uuid4())
    snapshot = {**doc, "_id": pointer, "workspace_id": workspace_id, "campaign_id": campaign_id,
                "version": current_version + 1, "updated_at": datetime.now(timezone.utc), "is_deleted": False}
    await db.outreach_sequence_versions.insert_one(snapshot)
    revision_filter = expected_revision if "authorization_revision" in campaign else {"$exists": False}
    published = await db.outreach_campaigns.update_one(
        {"id": campaign_id, "workspace_id": workspace_id, "status": campaign["status"],
         "is_deleted": {"$ne": True}, "authorization_revision": revision_filter},
        {"$set": {"sequence_version_id": pointer, "updated_at": snapshot["updated_at"]},
         "$inc": {"authorization_revision": 1}},
    )
    if getattr(published, "matched_count", 0) == 0:
        return False
    projection = {k: v for k, v in snapshot.items() if k != "_id"}
    try:
        if isinstance(current, dict) and not campaign.get("sequence_version_id"):
            await db.outreach_sequences.update_one(
                {"workspace_id": workspace_id, "campaign_id": campaign_id}, {"$set": projection},
            )
        else:
            existing_projection = await db.outreach_sequences.find_one({"workspace_id": workspace_id, "campaign_id": campaign_id})
            if isinstance(existing_projection, dict):
                await db.outreach_sequences.update_one(
                    {"workspace_id": workspace_id, "campaign_id": campaign_id, "$or": [
                        {"version": {"$exists": False}}, {"version": {"$lt": snapshot["version"]}},
                    ]}, {"$set": projection},
                )
            else:
                await db.outreach_sequences.insert_one({"_id": f"sequence:{workspace_id}:{campaign_id}", **projection})
    except DuplicateKeyError:
        # A concurrent newer projection is harmless: readers use the pointer.
        pass
    except Exception as exc:
        logger.warning("Saved sequence projection needs repair (%s)", type(exc).__name__)
    return True
