import pytest

from api.routes import calendar_notes as calendar_notes_routes


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *_args, **_kwargs):
        self._docs = sorted(self._docs, key=lambda doc: doc.get("date", ""))
        return self

    async def to_list(self, _length=None):
        return list(self._docs)


class FakeCalendarNotesCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.inserted = []

    def find(self, query, *_args, **_kwargs):
        workspace_id = query.get("workspace_id")
        month_filter = query.get("date", {}).get("$regex", "").lstrip("^")
        filtered = [
            doc for doc in self.docs
            if doc.get("workspace_id") == workspace_id
            and (not month_filter or str(doc.get("date", "")).startswith(month_filter))
        ]
        return FakeCursor(filtered)

    async def insert_one(self, doc):
        self.inserted.append(dict(doc))
        self.docs.append(dict(doc))


class FakeDB:
    def __init__(self, docs=None):
        self.calendar_notes = FakeCalendarNotesCollection(docs)


@pytest.mark.asyncio
async def test_list_calendar_notes_normalizes_legacy_note_shapes():
    db = FakeDB([
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
