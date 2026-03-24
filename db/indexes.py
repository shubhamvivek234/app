"""
Phase 0.1 — MongoDB Index Definitions
Run once on DB setup. Never rely on auto-indexing.
"""
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from db.mongo import get_client

logger = logging.getLogger(__name__)


async def _safe_create_index(collection, keys, **kwargs) -> None:
    """Create index, ignoring conflicts with pre-existing indexes of different names."""
    try:
        await collection.create_index(keys, **kwargs)
    except Exception as exc:
        # IndexOptionsConflict (85/86) — index exists with different name, safe to ignore
        # DuplicateKeyError (11000) - unique index creation failed due to existing duplicates, ignore for local/dev
        if "already exists" in str(exc) or getattr(exc, "code", None) in (85, 86, 11000):
            logger.warning("Index creation skipped on %s (code %s): %s", collection.name, getattr(exc, "code", None), exc)
        else:
            raise


async def create_all_indexes(client: AsyncIOMotorClient | None = None) -> None:
    if client is None:
        client = await get_client()

    import os
    db = client[os.environ["DB_NAME"]]

    # posts
    await _safe_create_index(db.posts, [("status", 1), ("scheduled_time", 1)])
    await _safe_create_index(db.posts, [("user_id", 1), ("status", 1), ("created_at", -1)])
    await _safe_create_index(db.posts, [("workspace_id", 1), ("status", 1), ("scheduled_time", 1)])
    await _safe_create_index(db.posts, [("deleted_at", 1)], expireAfterSeconds=2592000)  # 30-day TTL
    # Subscription grace period: paused post queries (user_id + status + paused_reason)
    await _safe_create_index(db.posts, [("user_id", 1), ("status", 1), ("paused_reason", 1)])
    await _safe_create_index(db.posts, [("user_id", 1), ("status", 1), ("paused_reason", 1), ("scheduled_time", 1)])

    # users — subscription lifecycle queries (full table scans without these)
    await _safe_create_index(db.users, [("subscription_expires_at", 1), ("subscription_status", 1)])
    await _safe_create_index(db.users, [("subscription_cleanup_date", 1), ("subscription_status", 1)])
    await _safe_create_index(db.users, [("subscription_status", 1), ("subscription_expires_at", 1)])
    # Webhook lookup indexes (Stripe + Razorpay match by customer ID and email)
    await _safe_create_index(db.users, [("email", 1)], unique=True)
    await _safe_create_index(db.users, [("stripe_customer_id", 1)])
    await _safe_create_index(db.users, [("razorpay_customer_id", 1)])

    # notifications
    await _safe_create_index(db.notifications, [("user_id", 1), ("is_read", 1), ("created_at", -1)])

    # social_accounts
    await _safe_create_index(db.social_accounts, [("user_id", 1), ("platform", 1), ("is_active", 1)])

    # payment_transactions
    await _safe_create_index(db.payment_transactions, [("user_id", 1), ("created_at", -1)])

    # user_sessions — TTL 30 days
    await _safe_create_index(db.user_sessions, [("created_at", 1)], expireAfterSeconds=2592000)

    # audit_events indexes are managed exclusively by db/audit_events.py:ensure_indexes()
    # which is called separately from api/main.py lifespan. Do not add audit_events
    # indexes here — the authoritative field is created_at/expires_at, not timestamp.

    # media_assets
    await _safe_create_index(db.media_assets, [("user_id", 1), ("status", 1)])
    await _safe_create_index(db.media_assets, [("post_id", 1)])

    # webhook_events (dedup) — compound index on (platform, event_id) because different
    # platforms can share the same event_id value. sparse=True skips docs with null event_id.
    await _safe_create_index(db.webhook_events, [("platform", 1), ("event_id", 1)], unique=True, sparse=True)
    await _safe_create_index(db.webhook_events, [("created_at", 1)], expireAfterSeconds=604800)  # 7-day TTL

    # workspaces / workspace_members
    await _safe_create_index(db.workspaces, [("owner_id", 1)])
    await _safe_create_index(db.workspace_members, [("workspace_id", 1), ("user_id", 1)], unique=True)

    logger.info("All MongoDB indexes created successfully")


if __name__ == "__main__":
    asyncio.run(create_all_indexes())
