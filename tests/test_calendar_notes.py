from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException

from api.routes import calendar_notes as calendar_notes_routes


def _matches_value(val, expected):
    if isinstance(expected, dict):
        if "$gt" in expected:
            return val is not None and str(val) > str(expected["$gt"])
        if "$exists" in expected:
            return (val is not None) == bool(expected["$exists"])
        if "$in" in expected:
            return val in expected["$in"]
        if "$regex" in expected:
            prefix = expected["$regex"].lstrip("^")
            return str(val or "").startswith(prefix)
    return val == expected


def _matches_query(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches_query(doc, cond) for cond in expected):
                return False
            continue
        if not _matches_value(doc.get(key), expected):
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction=1):
        self._docs = sorted(self._docs, key=lambda doc: doc.get(key, ""))
        if direction == -1:
            self._docs.reverse()
        return self

    async def to_list(self, _length=None):
        return list(self._docs)


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]
        self.inserted = []

    def find(self, query=None, *_args, **_kwargs):
        query = query or {}
        filtered = [d for d in self.docs if _matches_query(d, query)]
        return FakeCursor(filtered)

    async def find_one(self, query=None, *_args, **_kwargs):
        query = query or {}
        for d in self.docs:
            if _matches_query(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc):
        stored = dict(doc)
        self.inserted.append(stored)
        self.docs.append(stored)

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _matches_query(d, query):
                self.docs.pop(i)
                class Result:
                    deleted_count = 1
                return Result()
        class Result:
            deleted_count = 0
        return Result()

    async def delete_many(self, query):
        original_count = len(self.docs)
        self.docs = [d for d in self.docs if not _matches_query(d, query)]
        class Result:
            deleted_count = original_count - len(self.docs)
        return Result()


class FakeDB:
    def __init__(self, notes=None, shares=None, posts=None, workspaces=None, users=None):
        self.calendar_notes = FakeCollection(notes)
        self.calendar_shares = FakeCollection(shares)
        self.posts = FakeCollection(posts)
        self.workspaces = FakeCollection(workspaces)
        self.users = FakeCollection(users)


@pytest.mark.asyncio
async def test_list_calendar_notes_normalizes_legacy_note_shapes():
    db = FakeDB(notes=[
        {
            "note_id": "note-1",
            "workspace_id": "ws-1",
            "date": "2026-06-03",
            "note": "Launch prep",
            "color": "#4CAF50",
        },
        {
            "id": "note-2",
            "workspace_id": "ws-1",
            "date": "2026-05-28",
            "text": "Old format",
            "color": "blue",
        },
    ])

    result = await calendar_notes_routes.list_calendar_notes(
        current_user={"user_id": "user-1", "default_workspace_id": "ws-1"},
        db=db,
        month="2026-06",
    )

    assert result == [
        {
            "note_id": "note-1",
            "id": "note-1",
            "workspace_id": "ws-1",
            "date": "2026-06-03",
            "note": "Launch prep",
            "text": "Launch prep",
            "color": "green",
        }
    ]


@pytest.mark.asyncio
async def test_create_calendar_note_accepts_text_alias_and_hex_color():
    db = FakeDB()

    body = calendar_notes_routes.CalendarNoteCreate(
        date="2026-06-05",
        text="Client approval follow-up",
        color="#2196F3",
    )

    result = await calendar_notes_routes.create_calendar_note(
        body=body,
        current_user={"user_id": "user-1", "default_workspace_id": "ws-1"},
        db=db,
    )

    assert db.calendar_notes.inserted[0]["note"] == "Client approval follow-up"
    assert db.calendar_notes.inserted[0]["color"] == "blue"
    assert result["text"] == "Client approval follow-up"
    assert result["note"] == "Client approval follow-up"
    assert result["color"] == "blue"
    assert result["workspace_id"] == "ws-1"


@pytest.mark.asyncio
async def test_create_calendar_share_with_none_body_uses_defaults():
    db = FakeDB()

    result = await calendar_notes_routes.create_calendar_share(
        current_user={"user_id": "user-1", "default_workspace_id": "ws-1"},
        db=db,
        body=None,
    )

    assert "token" in result
    assert result["token"]
    assert "expires_at" in result
    assert len(db.calendar_shares.docs) == 1


@pytest.mark.asyncio
async def test_create_calendar_share_reuses_existing_active_token():
    future_date = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
    db = FakeDB(shares=[
        {
            "token": "existing-token-123",
            "workspace_id": "ws-1",
            "created_by": "user-1",
            "expires_at": future_date,
        }
    ])

    result = await calendar_notes_routes.create_calendar_share(
        current_user={"user_id": "user-1", "default_workspace_id": "ws-1"},
        db=db,
        body=calendar_notes_routes.CalendarShareCreate(regenerate=False),
    )

    assert result["token"] == "existing-token-123"
    assert len(db.calendar_shares.docs) == 1


@pytest.mark.asyncio
async def test_create_calendar_share_regenerates_when_requested():
    future_date = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
    db = FakeDB(shares=[
        {
            "token": "existing-token-123",
            "workspace_id": "ws-1",
            "created_by": "user-1",
            "expires_at": future_date,
        }
    ])

    result = await calendar_notes_routes.create_calendar_share(
        current_user={"user_id": "user-1", "default_workspace_id": "ws-1"},
        db=db,
        body=calendar_notes_routes.CalendarShareCreate(regenerate=True),
    )

    assert result["token"] != "existing-token-123"
    assert len(db.calendar_shares.docs) == 2


@pytest.mark.asyncio
async def test_get_calendar_share_and_revoke():
    future_date = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
    db = FakeDB(shares=[
        {
            "token": "tok-456",
            "workspace_id": "ws-1",
            "expires_at": future_date,
        }
    ])

    share = await calendar_notes_routes.get_calendar_share(
        current_user={"user_id": "user-1", "default_workspace_id": "ws-1"},
        db=db,
    )
    assert share["token"] == "tok-456"

    await calendar_notes_routes.revoke_calendar_share(
        current_user={"user_id": "user-1", "default_workspace_id": "ws-1"},
        db=db,
    )
    assert len(db.calendar_shares.docs) == 0

    empty = await calendar_notes_routes.get_calendar_share(
        current_user={"user_id": "user-1", "default_workspace_id": "ws-1"},
        db=db,
    )
    assert empty["token"] is None


@pytest.mark.asyncio
async def test_get_public_calendar_success():
    future_date = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    db = FakeDB(
        shares=[
            {
                "token": "valid-public-token",
                "workspace_id": "ws-1",
                "created_by": "user-1",
                "expires_at": future_date,
            }
        ],
        posts=[
            {
                "id": "post-1",
                "workspace_id": "ws-1",
                "content": "Exciting launch day announcement!",
                "platforms": ["twitter", "linkedin"],
                "status": "scheduled",
                "scheduled_time": "2026-09-10T14:00:00Z",
            },
            {
                "id": "post-deleted",
                "workspace_id": "ws-1",
                "content": "Draft post",
                "status": "draft",
                "deleted_at": "2026-09-01T00:00:00Z",
            },
        ],
        notes=[
            {
                "note_id": "note-1",
                "workspace_id": "ws-1",
                "date": "2026-09-10",
                "note": "Launch stream starts at 2pm",
                "color": "green",
            }
        ],
        workspaces=[
            {
                "workspace_id": "ws-1",
                "name": "Acme Brand Studio",
            }
        ],
    )

    data = await calendar_notes_routes.get_public_calendar(
        token="valid-public-token",
        db=db,
    )

    assert data["workspace_name"] == "Acme Brand Studio"
    assert len(data["posts"]) == 1
    assert data["posts"][0]["id"] == "post-1"
    assert data["posts"][0]["content"] == "Exciting launch day announcement!"
    assert len(data["notes"]) == 1
    assert data["notes"][0]["note"] == "Launch stream starts at 2pm"


@pytest.mark.asyncio
async def test_get_public_calendar_invalid_token():
    db = FakeDB()
    with pytest.raises(HTTPException) as exc_info:
        await calendar_notes_routes.get_public_calendar(
            token="non-existent-token",
            db=db,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_public_calendar_expired_token():
    past_date = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    db = FakeDB(shares=[
        {
            "token": "expired-token",
            "workspace_id": "ws-1",
            "expires_at": past_date,
        }
    ])
    with pytest.raises(HTTPException) as exc_info:
        await calendar_notes_routes.get_public_calendar(
            token="expired-token",
            db=db,
        )
    assert exc_info.value.status_code == 410
