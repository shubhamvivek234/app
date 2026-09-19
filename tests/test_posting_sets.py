"""
Unit tests for Posting Sets (saved account groups).
"""
import pytest
from datetime import datetime, timezone
from api.models.posting_sets import (
    PostingSetCreate,
    PostingSetUpdate,
    PostingSetResponse,
)
from api.routes.posting_sets import (
    list_posting_sets,
    create_posting_set,
    update_posting_set,
    delete_posting_set,
)
from fastapi import HTTPException


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=100):
        return self.docs[:length]


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query, projection=None):
        results = []
        for d in self.docs:
            match = True
            if "workspace_id" in query and d.get("workspace_id") != query["workspace_id"]:
                match = False
            if match:
                res = dict(d)
                if projection and "_id" in projection and projection["_id"] == 0:
                    res.pop("_id", None)
                results.append(res)
        return FakeCursor(results)

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if "id" in query and d.get("id") == query["id"]:
                res = dict(d)
                if projection and "_id" in projection and projection["_id"] == 0:
                    res.pop("_id", None)
                return res
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return doc

    async def update_one(self, query, update):
        for d in self.docs:
            if "id" in query and d.get("id") == query["id"]:
                if "$set" in update:
                    d.update(update["$set"])
                return True
        return False

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if "id" in query and d.get("id") == query["id"]:
                self.docs.pop(i)
                class Result:
                    deleted_count = 1
                return Result()
        class Result:
            deleted_count = 0
        return Result()


class FakeDB:
    def __init__(self):
        self.posting_sets = FakeCollection()
        self.social_accounts = FakeCollection([
            {"account_id": "acc_twitter_1", "workspace_id": "ws_1", "platform": "twitter"},
            {"account_id": "acc_linkedin_1", "workspace_id": "ws_1", "platform": "linkedin"},
        ])


def test_posting_set_models():
    req = PostingSetCreate(
        name="Personal Brand",
        account_ids=["acc_1", "acc_2"],
        color="emerald",
    )
    assert req.name == "Personal Brand"
    assert len(req.account_ids) == 2
    assert req.color == "emerald"

    up = PostingSetUpdate(name="Renamed Brand")
    assert up.name == "Renamed Brand"
    assert up.account_ids is None


@pytest.mark.asyncio
async def test_posting_sets_crud_flow():
    db = FakeDB()
    user = {"user_id": "usr_test_1", "default_workspace_id": "ws_1"}

    # 1. Create set
    create_req = PostingSetCreate(
        name="Tech Outlets",
        account_ids=["acc_twitter_1", "acc_linkedin_1"],
        color="blue",
    )
    created = await create_posting_set(body=create_req, current_user=user, db=db)
    assert created.name == "Tech Outlets"
    assert created.account_ids == ["acc_twitter_1", "acc_linkedin_1"]
    assert created.workspace_id == "ws_1"
    set_id = created.id

    # 2. List sets
    listed = await list_posting_sets(current_user=user, db=db)
    assert len(listed) == 1
    assert listed[0].id == set_id

    # 3. Update set
    update_req = PostingSetUpdate(name="Tech & SaaS Outlets", color="purple")
    updated = await update_posting_set(set_id=set_id, body=update_req, current_user=user, db=db)
    assert updated.name == "Tech & SaaS Outlets"
    assert updated.color == "purple"

    # 4. Delete set
    await delete_posting_set(set_id=set_id, current_user=user, db=db)
    after_del = await list_posting_sets(current_user=user, db=db)
    assert len(after_del) == 0


@pytest.mark.asyncio
async def test_posting_set_not_found():
    db = FakeDB()
    user = {"user_id": "usr_test_1", "default_workspace_id": "ws_1"}
    with pytest.raises(HTTPException) as exc:
        await update_posting_set(set_id="nonexistent", body=PostingSetUpdate(name="Test"), current_user=user, db=db)
    assert exc.value.status_code == 404
