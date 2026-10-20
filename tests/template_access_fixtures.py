"""Populate the real catalog access reader's current identity observations.

Legacy route tests may isolate mutation persistence; reads still exercise the
production UID/member/erasure checks rather than stubbing inspect_access.
"""
from unittest.mock import AsyncMock, MagicMock

from bson import ObjectId


def seed_catalog_access(db, actor, workspace, uid):
    user = {"_id": ObjectId(), "user_id": actor, "firebase_uid": uid, "status": "active"}
    member = {"workspace_id": workspace, "user_id": actor, "role": "admin", "status": "active"}
    for name, rows in (("users", [user]), ("workspace_members", [member])):
        collection = MagicMock()
        collection.find.return_value.limit.return_value.to_list = AsyncMock(return_value=rows)
        setattr(db, name, collection)
    db.account_erasure_tombstones.find_one = AsyncMock(return_value=None)
    db.outreach_suppression_guards.find_one = AsyncMock(return_value=None)
    return user, member
