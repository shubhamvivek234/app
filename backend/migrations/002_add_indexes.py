"""
Migration 002: Add compound indexes for performance.
Addendum Section A.3 — keep on M10 with right indexes.
"""
from pymongo import ASCENDING, DESCENDING


async def up(db):
    """Create compound indexes."""
    # Posts: fast lookup by user + status + scheduled_time
    await db.posts.create_index(
        [("user_id", ASCENDING), ("status", ASCENDING), ("scheduled_time", ASCENDING)],
        name="posts_user_status_scheduled",
        background=True,
    )
    # Posts: fast lookup by user + created_at for feed
    await db.posts.create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)],
        name="posts_user_created",
        background=True,
    )
    # Notifications: unread by user
    await db.notifications.create_index(
        [("user_id", ASCENDING), ("is_read", ASCENDING), ("created_at", DESCENDING)],
        name="notifications_user_unread",
        background=True,
    )
    # Social accounts: by user + platform
    await db.social_accounts.create_index(
        [("user_id", ASCENDING), ("platform", ASCENDING)],
        name="social_accounts_user_platform",
        background=True,
    )
    print("  ✅ Created all compound indexes")


async def down(db):
    """Drop compound indexes (keeping default _id index)."""
    for coll, name in [
        ("posts", "posts_user_status_scheduled"),
        ("posts", "posts_user_created"),
        ("notifications", "notifications_user_unread"),
        ("social_accounts", "social_accounts_user_platform"),
    ]:
        try:
            await db[coll].drop_index(name)
        except Exception:
            pass
    print("  ✅ Dropped compound indexes")
