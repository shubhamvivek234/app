"""
Migration 005: Add indexes for media_assets collection.
Stage 2.4 — Media pipeline.
"""
from pymongo import ASCENDING, DESCENDING


async def up(db):
    await db.media_assets.create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)],
        name="media_assets_user_date",
        background=True,
    )
    await db.media_assets.create_index(
        [("user_id", ASCENDING), ("type", ASCENDING)],
        name="media_assets_user_type",
        background=True,
    )
    # Add lifecycle status field to existing media_assets (quarantine/active/deleted)
    result = await db.media_assets.update_many(
        {"lifecycle_status": {"$exists": False}},
        {"$set": {"lifecycle_status": "active"}}
    )
    print(f"  Added lifecycle_status to {result.modified_count} media_assets")
    print("  media_assets indexes ready")


async def down(db):
    await db.media_assets.drop_index("media_assets_user_date")
    await db.media_assets.drop_index("media_assets_user_type")
    await db.media_assets.update_many({}, {"$unset": {"lifecycle_status": ""}})
