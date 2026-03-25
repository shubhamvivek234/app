"""
Phase 3.5.2 + EC18 — Proactive OAuth token refresh service.
Runs every 6 hours. Uses distributed Redis lock to prevent race conditions.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from celery_workers.celery_app import celery_app
from utils.encryption import decrypt, encrypt

logger = logging.getLogger(__name__)


@celery_app.task(
    name="celery_workers.tasks.tokens.refresh_expiring_tokens",
    bind=True,
    acks_late=True,
)
def refresh_expiring_tokens(self) -> dict:
    import asyncio
    return asyncio.get_event_loop().run_until_complete(_async_refresh_tokens())


async def _async_refresh_tokens() -> dict:
    from db.mongo import get_client

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    horizon = datetime.now(timezone.utc) + timedelta(hours=72)
    cursor = db.social_accounts.find(
        {"is_active": True, "token_expiry": {"$lt": horizon}},
        {"_id": 0, "account_id": 1, "platform": 1, "user_id": 1},
    )

    refreshed = 0
    failed = 0

    async for account in cursor:
        account_id = account["account_id"]
        platform = account["platform"]
        try:
            await _refresh_with_lock(db, account_id, platform)
            refreshed += 1
        except Exception as exc:
            logger.error("Token refresh failed for %s/%s: %s", account_id, platform, exc)
            failed += 1

    return {"refreshed": refreshed, "failed": failed}


async def _refresh_with_lock(db, account_id: str, platform: str) -> None:
    """
    EC18 — Distributed lock prevents concurrent token refresh.
    Re-reads token inside lock — another worker may have already refreshed it.
    """
    from db.redis_client import get_cache_redis
    from platform_adapters import get_adapter

    r = get_cache_redis()
    lock_key = f"token_refresh_lock:{account_id}"

    async with r.lock(lock_key, timeout=30, blocking_timeout=25):
        # Re-read inside lock — another worker may have refreshed already
        account = await db.social_accounts.find_one(
            {"account_id": account_id},
            {"_id": 0, "token_expiry": 1, "refresh_token": 1, "access_token": 1},
        )
        if not account:
            return

        # Still expired? If another worker refreshed, we skip
        if account.get("token_expiry") and account["token_expiry"] > datetime.now(timezone.utc) + timedelta(hours=72):
            logger.debug("Token for %s already refreshed by another worker", account_id)
            return

        refresh_token_enc = account.get("refresh_token")
        if not refresh_token_enc:
            # No refresh token — send user email to reconnect
            await _notify_reconnect_needed(db, account_id, platform)
            return

        refresh_token = decrypt(refresh_token_enc)
        adapter = get_adapter(platform)
        new_tokens = await adapter.refresh_token(refresh_token)

        # Encrypt before storage
        await db.social_accounts.update_one(
            {"account_id": account_id},
            {"$set": {
                "access_token": encrypt(new_tokens["access_token"]),
                "refresh_token": encrypt(new_tokens.get("refresh_token", refresh_token)),
                "token_expiry": new_tokens.get("expires_at"),
            }},
        )
        logger.info("Token refreshed for %s/%s", account_id, platform)


async def _notify_reconnect_needed(db, account_id: str, platform: str) -> None:
    account = await db.social_accounts.find_one({"account_id": account_id}, {"user_id": 1})
    if account:
        # TODO: integrate with notification service
        logger.info("Sending reconnect notification to user %s for %s", account.get("user_id"), platform)
