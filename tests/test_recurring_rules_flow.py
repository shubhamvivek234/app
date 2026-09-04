"""
Unit tests for recurring rules API endpoints and instance spawning:
- POST /recurring-rules with frontend payload (missing name, integer days_of_week)
- GET /recurring-rules with status & upcoming_count
- PATCH /recurring-rules/{rule_id} for pausing/resuming
- DELETE /recurring-rules/{rule_id} cleanup
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from api.routes.recurring import (
    RecurringRuleCreate,
    RecurringRuleUpdate,
    create_recurring_rule,
    list_recurring_rules,
    update_recurring_rule,
    delete_recurring_rule,
)


class FakeCursor:
    def __init__(self, items):
        self.items = list(items)

    async def to_list(self, length=None):
        return list(self.items)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    def __init__(self, initial=None):
        self.items = list(initial or [])

    def find(self, query=None, projection=None, *args, **kwargs):
        matched = []
        for item in self.items:
            match = True
            for k, v in (query or {}).items():
                if k == "$or":
                    if not any(all(item.get(sub_k) == sub_v for sub_k, sub_v in branch.items()) for branch in v):
                        match = False
                        break
                elif "." in k:
                    parts = k.split(".")
                    cur = item
                    for p in parts:
                        cur = cur.get(p) if isinstance(cur, dict) else None
                    if cur != v:
                        match = False
                        break
                elif isinstance(v, dict) and "$in" in v:
                    if item.get(k) not in v["$in"]:
                        match = False
                        break
                elif isinstance(v, dict) and "$ne" in v:
                    if item.get(k) == v["$ne"]:
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                matched.append(dict(item))
        return FakeCursor(matched)

    async def find_one(self, query=None, projection=None, *args, **kwargs):
        cursor = self.find(query, projection)
        if cursor.items:
            return dict(cursor.items[0])
        return None

    async def count_documents(self, query=None):
        return len(self.find(query).items)

    async def insert_one(self, doc):
        self.items.append(dict(doc))
        return MagicMock(inserted_id=doc.get("id") or "inserted_id")

    async def update_one(self, query, update, upsert=False):
        for item in self.items:
            match = True
            for k, v in query.items():
                if item.get(k) != v:
                    match = False
                    break
            if match:
                if "$set" in update:
                    item.update(update["$set"])
                return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)

    async def find_one_and_update(self, query, update, return_document=True, projection=None):
        for item in self.items:
            match = True
            for k, v in query.items():
                if k == "$or":
                    if not any(all(item.get(sub_k) == sub_v for sub_k, sub_v in branch.items()) for branch in v):
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                if "$set" in update:
                    item.update(update["$set"])
                return dict(item)
        return None

    async def delete_one(self, query):
        for i, item in enumerate(self.items):
            match = True
            for k, v in query.items():
                if k == "$or":
                    if not any(all(item.get(sub_k) == sub_v for sub_k, sub_v in branch.items()) for branch in v):
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if match:
                self.items.pop(i)
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    async def delete_many(self, query):
        initial_len = len(self.items)
        remaining = []
        for item in self.items:
            match = True
            for k, v in query.items():
                if k == "$or":
                    if not any(all(item.get(sub_k) == sub_v for sub_k, sub_v in branch.items()) for branch in v):
                        match = False
                        break
                elif item.get(k) != v:
                    match = False
                    break
            if not match:
                remaining.append(item)
        self.items = remaining
        return MagicMock(deleted_count=initial_len - len(remaining))


class FakeDB:
    def __init__(self):
        self.recurring_rules = FakeCollection()
        self.posts = FakeCollection()


@pytest.mark.asyncio
async def test_recurring_rule_create_with_frontend_payload():
    db = FakeDB()
    user = {"user_id": "usr_1", "default_workspace_id": "ws_1"}

    # Exact payload frontend sends (NO name, integer days_of_week)
    payload = RecurringRuleCreate(
        content="Every Monday morning growth marketing tip!",
        platforms=["instagram", "twitter"],
        accounts=["acc_1", "acc_2"],
        frequency="weekly",
        days_of_week=[1],
        day_of_month=1,
        time_of_day="09:00",
        ai_remix=True,
    )

    rule = await create_recurring_rule(body=payload, current_user=user, db=db)

    assert rule["id"] is not None
    assert rule["status"] == "active"
    assert rule["is_active"] is True
    assert rule["name"] == "Every Monday morning growth marketing ti..."
    assert rule["content"] == "Every Monday morning growth marketing tip!"
    assert rule["ai_remix"] is True

    # Check template was inserted in posts
    tmpl = await db.posts.find_one({"status": "template", "recurrence_rule_id": rule["id"]})
    assert tmpl is not None
    assert tmpl["recurrence"]["enabled"] is True
    assert tmpl["recurrence"]["frequency"] == "weekly"


@pytest.mark.asyncio
async def test_recurring_rule_toggle_pause_resume():
    db = FakeDB()
    user = {"user_id": "usr_1", "default_workspace_id": "ws_1"}

    create_payload = RecurringRuleCreate(
        content="Daily checkin",
        platforms=["twitter"],
        frequency="daily",
        time_of_day="10:00",
    )
    rule = await create_recurring_rule(body=create_payload, current_user=user, db=db)
    rule_id = rule["id"]

    # Frontend sends { status: "paused" }
    update_payload = RecurringRuleUpdate(status="paused")
    updated = await update_recurring_rule(rule_id=rule_id, body=update_payload, current_user=user, db=db)

    assert updated["status"] == "paused"
    assert updated["is_active"] is False

    # Resume: frontend sends { status: "active" }
    resume_payload = RecurringRuleUpdate(status="active")
    resumed = await update_recurring_rule(rule_id=rule_id, body=resume_payload, current_user=user, db=db)

    assert resumed["status"] == "active"
    assert resumed["is_active"] is True


@pytest.mark.asyncio
async def test_recurring_rule_delete():
    db = FakeDB()
    user = {"user_id": "usr_1", "default_workspace_id": "ws_1"}

    create_payload = RecurringRuleCreate(
        content="To be deleted",
        platforms=["twitter"],
    )
    rule = await create_recurring_rule(body=create_payload, current_user=user, db=db)
    rule_id = rule["id"]

    assert await db.recurring_rules.count_documents({"rule_id": rule_id}) == 1
    # 1 template + spawned scheduled instance(s)
    assert await db.posts.count_documents({"recurrence_rule_id": rule_id}) >= 1

    await delete_recurring_rule(rule_id=rule_id, current_user=user, db=db)

    assert await db.recurring_rules.count_documents({"rule_id": rule_id}) == 0
    assert await db.posts.count_documents({"recurrence_rule_id": rule_id}) == 0
