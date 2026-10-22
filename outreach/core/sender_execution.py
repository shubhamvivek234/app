"""Shared sender ownership; interrupted physical requests latch.

Preparation can expire. A possibly submitted request keeps ownership until the
worker completes or its outcome is explicitly reconciled. LinkedIn requests
share this record, which also holds the authoritative expiring permission.
"""
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from pymongo.errors import DuplicateKeyError

from outreach.core.authorization import canonical_hash
from outreach.core.execution_outbox import CLAIM_SECONDS


class SenderExecution:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    @staticmethod
    def scope(workspace_id: str, sender_id: str) -> dict:
        return {"_id": canonical_hash([workspace_id, sender_id]), "workspace_id": workspace_id, "sender_id": sender_id}

    async def acquire(self, workspace_id: str, sender_id: str, owner: str, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        scope = self.scope(workspace_id, sender_id)
        try:
            await self.db.outreach_sender_execution.insert_one({**scope, "status": "idle"})
        except DuplicateKeyError:
            pass
        result = await self.db.outreach_sender_execution.update_one(
            {**scope, "$or": [{"status": "idle"}, {"status": "preparing", "expires_at": {"$lte": now}}]},
            {"$set": {"status": "preparing", "owner_token": owner, "expires_at": now + timedelta(seconds=CLAIM_SECONDS)}},
        )
        return getattr(result, "matched_count", 0) == 1

    async def begin(self, workspace_id: str, sender_id: str, owner: str, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        result = await self.db.outreach_sender_execution.update_one(
            {**self.scope(workspace_id, sender_id), "owner_token": owner, "status": "preparing", "expires_at": {"$gt": now}},
            {"$set": {"status": "in_flight"}},
        )
        return getattr(result, "matched_count", 0) == 1

    async def release(self, workspace_id: str, sender_id: str, owner: str) -> bool:
        scope = {**self.scope(workspace_id, sender_id), "owner_token": owner}
        current = await self.db.outreach_sender_execution.find_one(scope)
        token = (current or {}).get("physical_request_token")
        if token:
            # A received response proves transport finished for this exact owner.
            # Unknown/in-flight tokens retain ownership for reconciliation.
            received = await self.db.outreach_physical_requests.find_one({"_id": token,
                "workspace_id": workspace_id, "sender_id": sender_id, "owner_token": owner, "status": "response_received"})
            if not received:
                return False
            cleared = await self.db.outreach_sender_execution.update_one({**scope, "physical_request_token": token},
                {"$unset": {"physical_request_token": ""}})
            if not cleared.matched_count:
                return False
        result = await self.db.outreach_sender_execution.update_one(
            {**scope, "physical_request_token": {"$exists": False}},
            {"$set": {"status": "idle"}, "$unset": {"owner_token": "", "expires_at": ""}},
        )
        return getattr(result, "matched_count", 0) == 1
