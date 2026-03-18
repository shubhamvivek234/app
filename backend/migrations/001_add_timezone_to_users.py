"""
Migration 001: Add timezone field to users collection.
Addendum Section B.6 — User Timezone Handling.
"""


async def up(db):
    """Add timezone field (default UTC) to all existing users."""
    result = await db.users.update_many(
        {"timezone": {"$exists": False}},
        {"$set": {"timezone": "UTC"}}
    )
    print(f"  Updated {result.modified_count} users with default timezone=UTC")


async def down(db):
    """Remove timezone field from all users."""
    result = await db.users.update_many(
        {},
        {"$unset": {"timezone": ""}}
    )
    print(f"  Removed timezone from {result.modified_count} users")
