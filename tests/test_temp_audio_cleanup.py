from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from utils import temp_audio_cleanup


class FakeCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def to_list(self, length=None):
        return self.docs if length is None else self.docs[:length]


def _get_nested(doc, key):
    current = doc
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _matches(doc, query):
    for key, expected in (query or {}).items():
        if key == "$or":
            if not any(_matches(doc, option) for option in expected):
                return False
            continue
        actual = _get_nested(doc, key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$nin" in expected and actual in expected["$nin"]:
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$lte" in expected and (actual is None or actual > expected["$lte"]):
                return False
            if "$exists" in expected:
                exists = actual is not None
                if exists != expected["$exists"]:
                    return False
            continue
        if actual != expected:
            return False
    return True


class FakeCollection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]
        self.updates = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    def find(self, query, projection=None, *args, **kwargs):
        limit = kwargs.get("limit") or 0
        docs = [dict(doc) for doc in self.docs if _matches(doc, query)]
        if limit:
            docs = docs[:limit]
        return FakeCursor(docs)

    async def update_one(self, query, update):
        self.updates.append((query, update))
        for doc in self.docs:
            if not _matches(doc, query):
                continue
            for key, value in (update.get("$set") or {}).items():
                doc[key] = value
            for key in (update.get("$unset") or {}).keys():
                doc.pop(key, None)
            return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


class FakeDb:
    def __init__(self, *, media_assets=None, posts=None):
        self.media_assets = FakeCollection(media_assets or [])
        self.posts = FakeCollection(posts or [])


@pytest.mark.asyncio
async def test_delete_temporary_audio_asset_deletes_storage_and_marks_deleted(monkeypatch):
    deleted_refs = []

    async def fake_delete(ref):
        deleted_refs.append(ref)

    monkeypatch.setattr(temp_audio_cleanup, "delete_file_async", fake_delete)
    db = FakeDb(
        media_assets=[
            {
                "media_id": "audio-1",
                "user_id": "user-1",
                "workspace_id": "workspace-1",
                "asset_kind": "audio",
                "temporary": True,
                "purpose": temp_audio_cleanup.TEMP_AUDIO_PURPOSE,
                "status": "ready",
                "storage_key": "media/user-1/audio-1.m4a",
                "media_url": "https://cdn.example/audio-1.m4a",
            }
        ]
    )

    outcome = await temp_audio_cleanup.delete_temporary_audio_asset(
        db,
        media_id="audio-1",
        user_id="user-1",
        workspace_id="workspace-1",
        reason="composer_removed",
    )

    assert outcome == "deleted"
    assert set(deleted_refs) == {"media/user-1/audio-1.m4a", "https://cdn.example/audio-1.m4a"}
    assert db.media_assets.docs[0]["status"] == "deleted"
    assert db.media_assets.docs[0]["temporary_audio_state"] == "cleaned"
    assert "storage_key" not in db.media_assets.docs[0]
    assert "media_url" not in db.media_assets.docs[0]


@pytest.mark.asyncio
async def test_delete_temporary_audio_asset_skips_non_temp_library_audio(monkeypatch):
    deleted_refs = []

    async def fake_delete(ref):
        deleted_refs.append(ref)

    monkeypatch.setattr(temp_audio_cleanup, "delete_file_async", fake_delete)
    db = FakeDb(
        media_assets=[
            {
                "media_id": "library-audio",
                "user_id": "user-1",
                "workspace_id": "workspace-1",
                "asset_kind": "audio",
                "temporary": False,
                "status": "ready",
                "storage_key": "media/user-1/library-audio.m4a",
            }
        ]
    )

    outcome = await temp_audio_cleanup.delete_temporary_audio_asset(
        db,
        media_id="library-audio",
        user_id="user-1",
        workspace_id="workspace-1",
        reason="post_terminal",
    )

    assert outcome == "not_temporary_audio"
    assert deleted_refs == []
    assert db.media_assets.docs[0]["status"] == "ready"


@pytest.mark.asyncio
async def test_post_media_cleanup_deletes_render_source_audio_when_orphaned(monkeypatch):
    deleted_refs = []

    async def fake_delete(ref):
        deleted_refs.append(ref)

    monkeypatch.setattr(temp_audio_cleanup, "delete_file_async", fake_delete)
    db = FakeDb(
        media_assets=[
            {
                "media_id": "rendered-video",
                "user_id": "user-1",
                "workspace_id": "workspace-1",
                "asset_kind": "video",
                "audio_mix": {"audio_media_id": "temp-audio"},
                "source_provider": "audio_render",
            },
            {
                "media_id": "temp-audio",
                "user_id": "user-1",
                "workspace_id": "workspace-1",
                "asset_kind": "audio",
                "temporary": True,
                "purpose": temp_audio_cleanup.TEMP_AUDIO_PURPOSE,
                "status": "ready",
                "storage_key": "media/user-1/temp-audio.m4a",
            },
        ],
        posts=[
            {
                "id": "post-1",
                "user_id": "user-1",
                "workspace_id": "workspace-1",
                "media_ids": ["rendered-video"],
                "deleted_at": datetime.now(timezone.utc),
            }
        ],
    )

    result = await temp_audio_cleanup.cleanup_temporary_audio_for_post_media(
        db,
        post={"id": "post-1", "user_id": "user-1", "workspace_id": "workspace-1"},
        media_ids=["rendered-video"],
        reason="post_deleted",
        excluding_post_id="post-1",
    )

    assert result["deleted"] == 1
    assert deleted_refs == ["media/user-1/temp-audio.m4a"]


@pytest.mark.asyncio
async def test_stale_temp_audio_skips_when_rendered_video_is_still_on_active_post(monkeypatch):
    deleted_refs = []

    async def fake_delete(ref):
        deleted_refs.append(ref)

    monkeypatch.setattr(temp_audio_cleanup, "delete_file_async", fake_delete)
    now = datetime.now(timezone.utc)
    db = FakeDb(
        media_assets=[
            {
                "media_id": "rendered-video",
                "user_id": "user-1",
                "workspace_id": "workspace-1",
                "asset_kind": "video",
                "audio_mix": {"audio_media_id": "temp-audio"},
                "source_provider": "audio_render",
            },
            {
                "media_id": "temp-audio",
                "user_id": "user-1",
                "workspace_id": "workspace-1",
                "asset_kind": "audio",
                "temporary": True,
                "purpose": temp_audio_cleanup.TEMP_AUDIO_PURPOSE,
                "status": "ready",
                "storage_key": "media/user-1/temp-audio.m4a",
                "cleanup_after": now - timedelta(minutes=5),
            },
        ],
        posts=[
            {
                "id": "post-1",
                "user_id": "user-1",
                "workspace_id": "workspace-1",
                "media_ids": ["rendered-video"],
            }
        ],
    )

    result = await temp_audio_cleanup.cleanup_stale_temporary_audio_assets(db, now=now)

    assert result["deleted"] == 0
    assert result["skipped"] == 1
    assert deleted_refs == []
    assert db.media_assets.docs[1]["status"] == "ready"
