import pytest
from api.routes.analytics import (
    ReportExportRequest,
    ReportScheduleRequest,
    delete_report_schedule,
    export_branded_analytics_report,
    list_report_schedules,
    schedule_analytics_report,
)


class _FakeCursor:
    def __init__(self, items):
        self.items = list(items)

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeCollection:
    def __init__(self, items=None):
        self.docs = {d.get("id"): d for d in (items or [])}

    async def count_documents(self, query):
        return len(self.docs)

    def find(self, query):
        return _FakeCursor(self.docs.values())

    async def insert_one(self, doc):
        self.docs[doc["id"]] = doc
        return doc

    async def delete_one(self, query):
        sched_id = query.get("id")
        if sched_id in self.docs:
            del self.docs[sched_id]
            from types import SimpleNamespace
            return SimpleNamespace(deleted_count=1)
        from types import SimpleNamespace
        return SimpleNamespace(deleted_count=0)


class _FakeDB:
    def __init__(self):
        self.posts = _FakeCollection([
            {"id": "p1", "status": "published", "content": "Post 1", "platforms": ["twitter"]},
        ])
        self.social_accounts = _FakeCollection([
            {"id": "a1", "platform": "twitter", "username": "acme", "is_active": True},
        ])
        self.analytics_schedules = _FakeCollection()


@pytest.mark.asyncio
async def test_export_branded_analytics_report():
    db = _FakeDB()
    user = {"user_id": "u1", "default_workspace_id": "ws_1"}
    req = ReportExportRequest(
        agency_name="Premier Social Agency",
        client_name="Nike",
    )
    report = await export_branded_analytics_report(req, current_user=user, db=db)
    assert report["agency_name"] == "Premier Social Agency"
    assert report["client_name"] == "Nike"
    assert report["metrics"]["total_published_posts"] == 1
    assert len(report["channels"]) == 1


@pytest.mark.asyncio
async def test_schedule_analytics_report_crud():
    db = _FakeDB()
    user = {"user_id": "u1", "default_workspace_id": "ws_1"}
    req = ReportScheduleRequest(
        recipient_email="client@example.com",
        client_name="Nike",
        frequency="monthly",
    )
    res = await schedule_analytics_report(req, current_user=user, db=db)
    assert res["ok"] is True

    schedules = await list_report_schedules(current_user=user, db=db)
    assert len(schedules) == 1
    assert schedules[0]["recipient_email"] == "client@example.com"

    await delete_report_schedule(schedules[0]["id"], current_user=user, db=db)
    schedules_after = await list_report_schedules(current_user=user, db=db)
    assert len(schedules_after) == 0
