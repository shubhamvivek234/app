"""Analytics — overview and timeline aggregations."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])


@router.get("/analytics/overview")
async def analytics_overview(
    current_user: CurrentUser,
    db: DB,
    days: int = Query(30, ge=1, le=365),
):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    import asyncio

    async def _count(q):
        return await db.posts.count_documents(q)

    (total_published, total_scheduled, total_failed) = await asyncio.gather(
        _count({"workspace_id": workspace_id, "status": "published", "updated_at": {"$gte": since}}),
        _count({"workspace_id": workspace_id, "status": "scheduled"}),
        _count({"workspace_id": workspace_id, "status": "failed", "updated_at": {"$gte": since}}),
    )

    # Platform breakdown
    pipeline = [
        {"$match": {"workspace_id": workspace_id, "status": "published", "updated_at": {"$gte": since}}},
        {"$unwind": "$platforms"},
        {"$group": {"_id": "$platforms", "count": {"$sum": 1}}},
    ]
    platform_docs = await db.posts.aggregate(pipeline).to_list(None)
    platform_breakdown = {d["_id"]: d["count"] for d in platform_docs}

    return {
        "total_published": total_published,
        "total_scheduled": total_scheduled,
        "total_failed": total_failed,
        "platform_breakdown": platform_breakdown,
        "days": days,
    }


@router.get("/analytics/timeline")
async def analytics_timeline(
    current_user: CurrentUser,
    db: DB,
    days: int = Query(30, ge=1, le=365),
):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    since = datetime.now(timezone.utc) - timedelta(days=days)

    pipeline = [
        {"$match": {
            "workspace_id": workspace_id,
            "status": "published",
            "updated_at": {"$gte": since.isoformat()},
        }},
        {"$group": {
            "_id": {"$substr": ["$updated_at", 0, 10]},  # YYYY-MM-DD
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    docs = await db.posts.aggregate(pipeline).to_list(None)
    return {"timeline": [{"date": d["_id"], "count": d["count"]} for d in docs]}


@router.get("/analytics/engagement")
async def analytics_engagement(current_user: CurrentUser, db: DB):
    """Stub — engagement data requires platform API polling (future feature)."""
    return {"engagement": [], "message": "Platform engagement sync coming soon"}


@router.get("/analytics/demographics")
async def analytics_demographics(current_user: CurrentUser, db: DB):
    """Stub — demographics requires platform API polling (future feature)."""
    return {"demographics": [], "message": "Platform demographics sync coming soon"}
