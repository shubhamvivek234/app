from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api.routes import timeslots as timeslots_route
from utils.timeslots import (
    find_next_available_timeslot,
    normalize_timeslot_category,
    normalize_timeslot_clock,
    sort_timeslot_docs,
)


def test_normalize_timeslot_clock_rejects_invalid_minute():
    with pytest.raises(ValueError, match="minute must be one of 00, 15, 30, 45"):
        normalize_timeslot_clock("MONDAY", "09", "10", "AM")


def test_normalize_timeslot_category_defaults_to_category_one():
    assert normalize_timeslot_category(None) == "Category 1"


def test_sort_timeslot_docs_orders_by_day_then_time():
    docs = [
        {"day_of_week": "WEDNESDAY", "hour": "12", "minute": "15", "ampm": "PM"},
        {"day_of_week": "MONDAY", "hour": "12", "minute": "00", "ampm": "PM"},
        {"day_of_week": "MONDAY", "hour": "09", "minute": "15", "ampm": "AM"},
    ]

    sorted_docs = sort_timeslot_docs(docs)

    assert [doc["day_of_week"] for doc in sorted_docs] == ["MONDAY", "MONDAY", "WEDNESDAY"]
    assert [(doc["hour"], doc["minute"], doc["ampm"]) for doc in sorted_docs[:2]] == [
        ("09", "15", "AM"),
        ("12", "00", "PM"),
    ]


def test_find_next_available_timeslot_skips_taken_slot():
    now = datetime(2026, 5, 24, 8, 0, tzinfo=timezone.utc)  # Sunday
    slots = [
        {"day_of_week": "SUNDAY", "hour": "09", "minute": "00", "ampm": "AM"},
        {"day_of_week": "SUNDAY", "hour": "10", "minute": "00", "ampm": "AM"},
    ]
    occupied = {datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc).isoformat()}

    result = find_next_available_timeslot(slots, occupied, now=now)

    assert result == datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, _length):
        return list(self._docs)


class _FakeSocialAccountsCollection:
    def __init__(self, doc):
        self.doc = dict(doc)
        self.update_calls = []

    async def find_one(self, query, *_args, **_kwargs):
        identifiers = query["$and"][0]["$or"]
        allowed_owners = query["$and"][1]["$or"]
        identifier_match = any(
            (
                condition.get("account_id") == self.doc.get("account_id")
                or condition.get("id") == self.doc.get("id")
            )
            for condition in identifiers
        )
        owner_match = any(
            (
                condition.get("workspace_id") == self.doc.get("workspace_id")
                or condition.get("user_id") == self.doc.get("user_id")
            )
            for condition in allowed_owners
        )
        if query.get("is_active") and self.doc.get("is_active") and identifier_match and owner_match:
            return dict(self.doc)
        return None

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        if "$set" in update:
            self.doc.update(update["$set"])
        return SimpleNamespace(modified_count=1)


class _FakeTimeslotsCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc["timeslot_id"])

    def find(self, query, *_args, **_kwargs):
        matches = [
            dict(doc)
            for doc in self.docs
            if all(doc.get(key) == value for key, value in query.items())
        ]
        return _FakeCursor(matches)


class _FakeDB:
    def __init__(self, account_doc):
        self.social_accounts = _FakeSocialAccountsCollection(account_doc)
        self.timeslots = _FakeTimeslotsCollection()


@pytest.mark.asyncio
async def test_create_and_list_timeslot_accept_user_scoped_account_without_workspace_id():
    db = _FakeDB(
        {
            "account_id": "acct-1",
            "id": "acct-1",
            "user_id": "usr-1",
            "is_active": True,
        }
    )
    current_user = {
        "user_id": "usr-1",
        "default_workspace_id": "ws-1",
    }

    created = await timeslots_route.create_timeslot(
        timeslots_route.TimeslotCreate(
            account_id="acct-1",
            category="Category 1",
            day_of_week="MONDAY",
            hour="09",
            minute="15",
            ampm="AM",
        ),
        current_user,
        db,
    )
    listed = await timeslots_route.list_timeslots(current_user, db, account_id="acct-1", category="Category 1")

    assert created.account_id == "acct-1"
    assert created.day_of_week == "MONDAY"
    assert db.social_accounts.doc["workspace_id"] == "ws-1"
    assert db.social_accounts.update_calls
    assert len(listed.timeslots) == 1
    assert listed.timeslots[0].hour == "09"
