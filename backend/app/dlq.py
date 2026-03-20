"""
Dead Letter Queue (DLQ) — Stage 4.5
Posts that fail all 3 retries are moved to the DLQ for manual review.
The DLQ is a MongoDB collection (no extra infrastructure needed at launch stage).
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional


DLQ_COLLECTION = "dead_letter_queue"


async def move_to_dlq(
    db,
    post_doc: Dict[str, Any],
    final_error: str,
    error_code: Optional[str] = None,
):
    """
    Move a permanently failed post to the DLQ collection.
    Keeps the original post doc + adds DLQ metadata.
    """
    dlq_entry = {
        **post_doc,
        "dlq_moved_at": datetime.now(timezone.utc).isoformat(),
        "dlq_error": final_error,
        "dlq_error_code": error_code or "EC1:NETWORK_FAILURE",
        "dlq_retry_count": post_doc.get("retry_count", 0),
        "dlq_original_status": "failed",
        "dlq_reviewed": False,
    }
    # Remove MongoDB _id to allow fresh insert
    dlq_entry.pop("_id", None)
    await db[DLQ_COLLECTION].insert_one(dlq_entry)


async def get_dlq_items(db, user_id: str, limit: int = 50):
    """Get DLQ items for a user."""
    items = await db[DLQ_COLLECTION].find(
        {"user_id": user_id, "dlq_reviewed": False},
        {"_id": 0}
    ).sort("dlq_moved_at", -1).limit(limit).to_list(None)
    return items


async def retry_from_dlq(db, dlq_post_id: str, user_id: str):
    """Re-queue a DLQ item by resetting its status to 'scheduled'."""
    item = await db[DLQ_COLLECTION].find_one(
        {"id": dlq_post_id, "user_id": user_id}
    )
    if not item:
        return None

    # Reset the post in the posts collection
    await db.posts.update_one(
        {"id": dlq_post_id},
        {"$set": {
            "status": "scheduled",
            "retry_count": 0,
            "scheduled_time": datetime.now(timezone.utc).isoformat(),
        }}
    )
    # Mark as reviewed in DLQ
    await db[DLQ_COLLECTION].update_one(
        {"id": dlq_post_id},
        {"$set": {"dlq_reviewed": True, "dlq_requeued_at": datetime.now(timezone.utc).isoformat()}}
    )
    return item
