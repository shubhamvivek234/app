"""
Migration 006: Create api_keys collection with indexes.
Stage 9 — Public API Key Management.
"""
from pymongo import ASCENDING


async def up(db):
    await db.api_keys.create_index(
        [("key_hash", ASCENDING)],
        name="api_keys_hash",
        unique=True,
        sparse=True,
        background=True,
    )
    await db.api_keys.create_index(
        [("user_id", ASCENDING), ("deleted", ASCENDING)],
        name="api_keys_user_active",
        background=True,
    )
    print("  ✅ api_keys collection indexes created")


async def down(db):
    await db.api_keys.drop()
    print("  Dropped api_keys collection")
