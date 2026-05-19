from datetime import datetime, timezone

import pytest

from utils.schedule_density import check_schedule_density


class _FakePostsCollection:
    def __init__(self):
        self.queries = []

    async def count_documents(self, query):
        self.queries.append(query)
        return 0


class _FakeDB:
    def __init__(self):
        self.posts = _FakePostsCollection()


@pytest.mark.asyncio
async def test_schedule_density_uses_workspace_scope():
    db = _FakeDB()
    proposed_time = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)

    warnings = await check_schedule_density(
        db,
        workspace_id="ws_123",
        platforms=["instagram"],
        proposed_time=proposed_time,
    )

    assert warnings == []
    assert len(db.posts.queries) == 2
    for query in db.posts.queries:
        assert query["workspace_id"] == "ws_123"
        assert "user_id" not in query
        assert query["deleted_at"] == {"$exists": False}
