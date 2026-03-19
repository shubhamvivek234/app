"""
Phase 0.1 — MongoDB Index Definitions
Run once on DB setup. Never rely on auto-indexing.
"""
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from db.mongo import get_client

logger = logging.getLogger(__name__)


async def create_all_indexes(client: AsyncIOMotorClient | None = None) -> None:
    if client is None:
        client = await get_client()

    import os
    db = client[os.environ["DB_NAME"]]

    # posts
    await db.posts.create_index([("status", 1), ("scheduled_time", 1)])
    await db.posts.create_index([("user_id", 1), ("status", 1), ("created_at", -1)])
    await db.posts.create_index([("workspace_id", 1), ("status", 1), ("scheduled_time", 1)])
    await db.posts.create_index([("deleted_at", 1)], expireAfterSeconds=2592000)  # 30-day TTL

    # notifications
    await db.notifications.create_index([("user_id", 1), ("is_read", 1), ("created_at", -1)])

    # social_accounts
    await db.social_accounts.create_index([("user_id", 1), ("platform", 1), ("is_active", 1)])

    # payment_transactions
    await db.payment_transactions.create_index([("user_id", 1), ("created_at", -1)])

    # user_sessions — TTL 30 days
    await db.user_sessions.create_index([("created_at", 1)], expireAfterSeconds=2592000)

    # audit_events
    await db.audit_events.create_index([("workspace_id", 1), ("timestamp", -1)])
    await db.audit_events.create_index([("entity_id", 1), ("timestamp", -1)])
    await db.audit_events.create_index([("timestamp", 1)], expireAfterSeconds=7776000)  # 90-day TTL

    # media_assets
    await db.media_assets.create_index([("user_id", 1), ("status", 1)])
    await db.media_assets.create_index([("post_id", 1)])

    # webhook_events (dedup)
    await db.webhook_events.create_index([("event_id", 1)], unique=True)
    await db.webhook_events.create_index([("created_at", 1)], expireAfterSeconds=604800)  # 7-day TTL

    # workspaces / workspace_members
    await db.workspaces.create_index([("owner_id", 1)])
    await db.workspace_members.create_index([("workspace_id", 1), ("user_id", 1)], unique=True)

    logger.info("All MongoDB indexes created successfully")


if __name__ == "__main__":
    asyncio.run(create_all_indexes())
