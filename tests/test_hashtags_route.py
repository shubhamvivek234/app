from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api.routes import hashtags as hashtags_route


class _FakeCursor:
    def __init__(self, docs):
        self._docs = [dict(doc) for doc in docs]

    def sort(self, field, direction):
        reverse = direction == -1
        self._docs.sort(key=lambda doc: doc.get(field), reverse=reverse)
        return self

    async def to_list(self, length=None):
        if length is None:
            return list(self._docs)
        return list(self._docs)[:length]


class _FakeHashtagGroupsCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    def find(self, query, _projection=None):
        matched = [dict(doc) for doc in self.docs if doc.get("workspace_id") == query.get("workspace_id")]
        return _FakeCursor(matched)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc["id"])

    async def find_one_and_update(self, query, update, return_document=True, projection=None):
        for doc in self.docs:
            if doc.get("workspace_id") != query.get("workspace_id"):
                continue
            if doc.get("group_id") == query["$or"][0]["group_id"] or doc.get("id") == query["$or"][1]["id"]:
                doc.update(update.get("$set", {}))
                result = dict(doc)
                if projection and projection.get("_id") == 0:
                    result.pop("_id", None)
                return result
        return None

    async def delete_one(self, query):
        before = len(self.docs)
        self.docs = [
            doc
            for doc in self.docs
            if not (
                doc.get("workspace_id") == query.get("workspace_id")
                and (doc.get("group_id") == query["$or"][0]["group_id"] or doc.get("id") == query["$or"][1]["id"])
            )
        ]
        return SimpleNamespace(deleted_count=before - len(self.docs))


class _FakeDB:
    def __init__(self, docs=None):
        self.hashtag_groups = _FakeHashtagGroupsCollection(docs)


@pytest.mark.asyncio
async def test_create_list_and_update_group_preserve_platform_and_normalize_hashtags():
    db = _FakeDB()
    current_user = {"user_id": "user-1", "default_workspace_id": "workspace-1"}

    created = await hashtags_route.create_hashtag_group(
        hashtags_route.HashtagGroupCreate(
            name=" Launch tags ",
            hashtags=[" launch ", "#Launch", "growth", "", " #Video "],
            category=" Campaign ",
            platform="Instagram",
        ),
        current_user,
        db,
    )

    assert created["platform"] == "instagram"
    assert created["category"] == "Campaign"
    assert created["hashtags"] == ["#launch", "#growth", "#Video"]

    listed = await hashtags_route.list_hashtag_groups(current_user, db)
    assert len(listed) == 1
    assert listed[0]["platform"] == "instagram"

    updated = await hashtags_route.update_hashtag_group(
        created["id"],
        hashtags_route.HashtagGroupCreate(
            name="Launch Updated",
            hashtags=["sales", "#sales", "video"],
            category="",
            platform="youtube",
        ),
        current_user,
        db,
    )

    assert updated["platform"] == "youtube"
    assert updated["category"] == "general"
    assert updated["hashtags"] == ["#sales", "#video"]


@pytest.mark.asyncio
async def test_list_groups_is_newest_first():
    now = datetime.now(timezone.utc)
    docs = [
        {
            "id": "older",
            "group_id": "older",
            "name": "Older",
            "hashtags": ["#one"],
            "category": "general",
            "platform": "",
            "workspace_id": "workspace-1",
            "created_at": now.replace(year=2025),
            "updated_at": now.replace(year=2025),
        },
        {
            "id": "newer",
            "group_id": "newer",
            "name": "Newer",
            "hashtags": ["#two"],
            "category": "general",
            "platform": "instagram",
            "workspace_id": "workspace-1",
            "created_at": now,
            "updated_at": now,
        },
    ]
    db = _FakeDB(docs)
    current_user = {"user_id": "user-1", "default_workspace_id": "workspace-1"}

    listed = await hashtags_route.list_hashtag_groups(current_user, db)

    assert [group["id"] for group in listed] == ["newer", "older"]


@pytest.mark.asyncio
async def test_delete_group_stays_workspace_scoped():
    now = datetime.now(timezone.utc)
    docs = [
        {
            "id": "group-1",
            "group_id": "group-1",
            "name": "Mine",
            "hashtags": ["#mine"],
            "category": "general",
            "platform": "",
            "workspace_id": "workspace-1",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "group-2",
            "group_id": "group-2",
            "name": "Theirs",
            "hashtags": ["#theirs"],
            "category": "general",
            "platform": "",
            "workspace_id": "workspace-2",
            "created_at": now,
            "updated_at": now,
        },
    ]
    db = _FakeDB(docs)
    current_user = {"user_id": "user-1", "default_workspace_id": "workspace-1"}

    await hashtags_route.delete_hashtag_group("group-1", current_user, db)

    assert [doc["id"] for doc in db.hashtag_groups.docs] == ["group-2"]
