"""Dashboard stats — aggregate counts from posts + accounts."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_stats(current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    user_id = current_user["user_id"]

    # Run counts in parallel using asyncio
    import asyncio

    async def _count(collection, query):
        return await collection.count_documents(query)

    (
        total_posts,
        scheduled_posts,
        published_posts,
        draft_posts,
        failed_posts,
        total_accounts,
    ) = await asyncio.gather(
        _count(db.posts, {"workspace_id": workspace_id}),
        _count(db.posts, {"workspace_id": workspace_id, "status": "scheduled"}),
        _count(db.posts, {"workspace_id": workspace_id, "status": "published"}),
        _count(db.posts, {"workspace_id": workspace_id, "status": "draft"}),
        _count(db.posts, {"workspace_id": workspace_id, "status": "failed"}),
        _count(db.social_accounts, {"user_id": user_id, "is_active": True}),
    )

    return {
        "total_posts": total_posts,
        "scheduled_posts": scheduled_posts,
        "published_posts": published_posts,
        "draft_posts": draft_posts,
        "failed_posts": failed_posts,
        "total_accounts": total_accounts,
    }
