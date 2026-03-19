"""
Phase 10 -- Disaster Recovery Runbook (executable Python).

Provides health checks, stuck-post recovery, DLQ draining, Redis state
rebuilding, and data integrity verification. Each function is idempotent
and safe to run in production.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Posts stuck in "processing" longer than this are considered stuck
STUCK_THRESHOLD_MINUTES = 30

# Platform rate limit defaults (mirrored from utils/rate_limit.py)
PLATFORM_LIMITS: dict[str, dict[str, int]] = {
    "instagram": {"tokens_per_window": 25, "window_seconds": 3600},
    "facebook": {"tokens_per_window": 200, "window_seconds": 3600},
    "youtube": {"tokens_per_window": 6, "window_seconds": 86400},
    "twitter": {"tokens_per_window": 300, "window_seconds": 10800},
    "linkedin": {"tokens_per_window": 150, "window_seconds": 86400},
    "tiktok": {"tokens_per_window": 5, "window_seconds": 86400},
}


# ---------------------------------------------------------------------------
# System Health Check
# ---------------------------------------------------------------------------

async def check_system_health(db, redis_queue, redis_cache) -> dict[str, Any]:
    """
    Check health of all system components.

    Returns a structured dict with per-component status and an overall
    healthy/degraded/critical assessment.
    """
    components: dict[str, dict[str, Any]] = {}

    # MongoDB
    try:
        result = await db.command("ping")
        components["mongodb"] = {
            "status": "healthy",
            "ping": result.get("ok", 0) == 1,
        }
    except Exception as exc:
        components["mongodb"] = {"status": "critical", "error": str(exc)}

    # Redis Queue
    try:
        await redis_queue.ping()
        queue_info = await redis_queue.info("memory")
        components["redis_queue"] = {
            "status": "healthy",
            "used_memory_mb": round(
                queue_info.get("used_memory", 0) / (1024 * 1024), 2
            ),
        }
    except Exception as exc:
        components["redis_queue"] = {"status": "critical", "error": str(exc)}

    # Redis Cache
    try:
        await redis_cache.ping()
        cache_info = await redis_cache.info("memory")
        components["redis_cache"] = {
            "status": "healthy",
            "used_memory_mb": round(
                cache_info.get("used_memory", 0) / (1024 * 1024), 2
            ),
        }
    except Exception as exc:
        components["redis_cache"] = {"status": "critical", "error": str(exc)}

    # DLQ count
    try:
        dlq_count = await db.dead_letter_queue.count_documents({})
        components["dlq"] = {
            "status": "healthy" if dlq_count < 100 else "degraded",
            "count": dlq_count,
        }
    except Exception as exc:
        components["dlq"] = {"status": "unknown", "error": str(exc)}

    # Stuck posts
    try:
        threshold = datetime.now(timezone.utc) - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
        stuck_count = await db.posts.count_documents({
            "status": "processing",
            "updated_at": {"$lt": threshold},
        })
        components["scheduler"] = {
            "status": "healthy" if stuck_count == 0 else "degraded",
            "stuck_posts": stuck_count,
        }
    except Exception as exc:
        components["scheduler"] = {"status": "unknown", "error": str(exc)}

    # Overall assessment
    statuses = [c["status"] for c in components.values()]
    if "critical" in statuses:
        overall = "critical"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "components": components,
    }


# ---------------------------------------------------------------------------
# Stuck Post Recovery
# ---------------------------------------------------------------------------

async def recover_stuck_posts(db) -> int:
    """
    Find posts stuck in 'processing' state for longer than STUCK_THRESHOLD_MINUTES
    and reset them to 'scheduled' so they will be retried.

    Returns the count of recovered posts.
    """
    threshold = datetime.now(timezone.utc) - timedelta(minutes=STUCK_THRESHOLD_MINUTES)

    result = await db.posts.update_many(
        {
            "status": "processing",
            "updated_at": {"$lt": threshold},
        },
        {
            "$set": {
                "status": "scheduled",
                "updated_at": datetime.now(timezone.utc),
                "recovery_note": f"Auto-recovered from stuck processing at {datetime.now(timezone.utc).isoformat()}",
            },
            "$inc": {"recovery_count": 1},
        },
    )

    recovered = result.modified_count
    if recovered > 0:
        logger.warning("Recovered %d stuck posts (threshold: %d min)", recovered, STUCK_THRESHOLD_MINUTES)
    else:
        logger.info("No stuck posts found")

    return recovered


# ---------------------------------------------------------------------------
# DLQ Drain
# ---------------------------------------------------------------------------

async def drain_dlq(db) -> list[dict[str, Any]]:
    """
    Read all items from the dead letter queue and return a summary.

    Does NOT delete items -- returns them for review. Use acknowledge_dlq_items()
    to remove reviewed items.
    """
    items = await db.dead_letter_queue.find({}).to_list(length=None)

    summary: list[dict[str, Any]] = []
    for item in items:
        summary.append({
            "id": str(item.get("_id")),
            "post_id": str(item.get("post_id", "")),
            "platform": item.get("platform", "unknown"),
            "error": item.get("error", ""),
            "failed_at": item.get("failed_at", "").isoformat()
                if hasattr(item.get("failed_at", ""), "isoformat")
                else str(item.get("failed_at", "")),
            "retry_count": item.get("retry_count", 0),
        })

    logger.info("DLQ drain: found %d items", len(summary))
    return summary


async def acknowledge_dlq_items(db, item_ids: list[str]) -> int:
    """Remove reviewed DLQ items by their IDs."""
    from bson import ObjectId

    oids = [ObjectId(i) for i in item_ids]
    result = await db.dead_letter_queue.delete_many({"_id": {"$in": oids}})
    logger.info("Acknowledged %d DLQ items", result.deleted_count)
    return result.deleted_count


# ---------------------------------------------------------------------------
# Redis State Rebuild
# ---------------------------------------------------------------------------

async def rebuild_redis_state(db, redis) -> dict[str, Any]:
    """
    Reconstruct rate limit counters and circuit breaker states from MongoDB.

    This is a recovery operation for when Redis data is lost (restart, failover).
    Safe to run at any time -- resets to conservative defaults.
    """
    rebuilt: dict[str, Any] = {
        "rate_limits_reset": 0,
        "circuit_breakers_reset": 0,
        "rebuilt_at": datetime.now(timezone.utc).isoformat(),
    }

    # Reset rate limit counters to max tokens (conservative: allows posts)
    social_accounts = await db.social_accounts.find(
        {"status": "active"},
        {"platform": 1, "_id": 1},
    ).to_list(length=None)

    for account in social_accounts:
        platform = account.get("platform", "")
        account_id = str(account["_id"])
        limits = PLATFORM_LIMITS.get(platform)
        if limits:
            key = f"ratelimit:{platform}:{account_id}:tokens"
            await redis.setex(key, limits["window_seconds"], limits["tokens_per_window"])
            rebuilt["rate_limits_reset"] += 1

    # Reset all circuit breakers to CLOSED
    platforms = list(PLATFORM_LIMITS.keys())
    for platform in platforms:
        state_key = f"circuit:{platform}:state"
        failure_key = f"circuit:{platform}:failures"
        await redis.set(state_key, "closed")
        await redis.delete(failure_key)
        rebuilt["circuit_breakers_reset"] += 1

    logger.info(
        "Redis state rebuilt: %d rate limits, %d circuit breakers",
        rebuilt["rate_limits_reset"],
        rebuilt["circuit_breakers_reset"],
    )
    return rebuilt


# ---------------------------------------------------------------------------
# Data Integrity Verification
# ---------------------------------------------------------------------------

async def verify_data_integrity(db) -> dict[str, Any]:
    """
    Check for orphaned records, missing references, and version inconsistencies.

    Returns a structured report of any integrity issues found.
    """
    issues: list[dict[str, Any]] = []

    # 1. Posts referencing non-existent social accounts
    try:
        pipeline = [
            {"$lookup": {
                "from": "social_accounts",
                "localField": "social_account_id",
                "foreignField": "_id",
                "as": "account",
            }},
            {"$match": {"account": {"$size": 0}}},
            {"$project": {"_id": 1, "social_account_id": 1, "status": 1}},
            {"$limit": 100},
        ]
        orphaned_posts = await db.posts.aggregate(pipeline).to_list(length=100)
        if orphaned_posts:
            issues.append({
                "type": "orphaned_posts",
                "description": "Posts referencing non-existent social accounts",
                "count": len(orphaned_posts),
                "sample_ids": [str(p["_id"]) for p in orphaned_posts[:10]],
            })
    except Exception as exc:
        logger.warning("Orphaned posts check failed: %s", exc)

    # 2. Social accounts referencing non-existent workspaces
    try:
        pipeline = [
            {"$lookup": {
                "from": "workspaces",
                "localField": "workspace_id",
                "foreignField": "_id",
                "as": "workspace",
            }},
            {"$match": {"workspace": {"$size": 0}}},
            {"$project": {"_id": 1, "workspace_id": 1, "platform": 1}},
            {"$limit": 100},
        ]
        orphaned_accounts = await db.social_accounts.aggregate(pipeline).to_list(length=100)
        if orphaned_accounts:
            issues.append({
                "type": "orphaned_social_accounts",
                "description": "Social accounts referencing non-existent workspaces",
                "count": len(orphaned_accounts),
                "sample_ids": [str(a["_id"]) for a in orphaned_accounts[:10]],
            })
    except Exception as exc:
        logger.warning("Orphaned accounts check failed: %s", exc)

    # 3. Workspace members referencing non-existent users
    try:
        pipeline = [
            {"$unwind": "$members"},
            {"$lookup": {
                "from": "users",
                "localField": "members.user_id",
                "foreignField": "_id",
                "as": "user",
            }},
            {"$match": {"user": {"$size": 0}}},
            {"$project": {"_id": 1, "members.user_id": 1}},
            {"$limit": 100},
        ]
        orphaned_members = await db.workspaces.aggregate(pipeline).to_list(length=100)
        if orphaned_members:
            issues.append({
                "type": "orphaned_workspace_members",
                "description": "Workspace members referencing non-existent users",
                "count": len(orphaned_members),
                "sample_ids": [str(m["_id"]) for m in orphaned_members[:10]],
            })
    except Exception as exc:
        logger.warning("Orphaned members check failed: %s", exc)

    # 4. Posts with inconsistent status (published but no published_at timestamp)
    try:
        inconsistent = await db.posts.count_documents({
            "status": "published",
            "published_at": {"$exists": False},
        })
        if inconsistent > 0:
            issues.append({
                "type": "inconsistent_status",
                "description": "Posts marked 'published' without published_at timestamp",
                "count": inconsistent,
            })
    except Exception as exc:
        logger.warning("Status consistency check failed: %s", exc)

    # 5. Duplicate social account connections
    try:
        pipeline = [
            {"$group": {
                "_id": {
                    "workspace_id": "$workspace_id",
                    "platform": "$platform",
                    "platform_user_id": "$platform_user_id",
                },
                "count": {"$sum": 1},
                "ids": {"$push": "$_id"},
            }},
            {"$match": {"count": {"$gt": 1}}},
            {"$limit": 50},
        ]
        duplicates = await db.social_accounts.aggregate(pipeline).to_list(length=50)
        if duplicates:
            issues.append({
                "type": "duplicate_social_accounts",
                "description": "Duplicate social account connections in same workspace",
                "count": len(duplicates),
                "details": [
                    {
                        "platform": d["_id"]["platform"],
                        "duplicate_count": d["count"],
                    }
                    for d in duplicates[:10]
                ],
            })
    except Exception as exc:
        logger.warning("Duplicate accounts check failed: %s", exc)

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total_issues": len(issues),
        "healthy": len(issues) == 0,
        "issues": issues,
    }
