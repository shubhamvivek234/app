"""
Migration 003: Add platform_results and status_history to posts collection.
Stage 1.5/1.6 — Per-platform independent execution.
"""


async def up(db):
    """Add platform_results and status_history to existing posts."""
    # Add platform_results = {} to posts that don't have it
    result = await db.posts.update_many(
        {"platform_results": {"$exists": False}},
        {"$set": {"platform_results": {}}}
    )
    print(f"  Added platform_results to {result.modified_count} posts")

    # Add status_history = [] to posts that don't have it
    result = await db.posts.update_many(
        {"status_history": {"$exists": False}},
        {"$set": {"status_history": []}}
    )
    print(f"  Added status_history to {result.modified_count} posts")

    # Backfill status_history for already-published posts
    published = await db.posts.find(
        {"status": "published", "published_at": {"$exists": True}},
        {"id": 1, "published_at": 1, "platforms": 1}
    ).to_list(None)

    for post in published:
        entry = {
            "status": "published",
            "at": post.get("published_at", ""),
            "note": f"Backfilled — published to {', '.join(post.get('platforms', []))}",
        }
        await db.posts.update_one(
            {"id": post["id"], "status_history": []},
            {"$push": {"status_history": entry}}
        )
    print(f"  Backfilled status_history for {len(published)} published posts")


async def down(db):
    """Remove platform_results and status_history from posts."""
    result = await db.posts.update_many(
        {},
        {"$unset": {"platform_results": "", "status_history": ""}}
    )
    print(f"  Removed platform_results + status_history from {result.modified_count} posts")
