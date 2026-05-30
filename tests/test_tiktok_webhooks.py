from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.routes import webhooks


class FakePostsCollection:
    def __init__(self):
        self.update_calls = []

    async def find_one(self, query, *_args, **_kwargs):
        if query.get("platform_results.tiktok.platform_post_id") == "publish-123":
            return {
                "id": "post-1",
                "account_results": {
                    "tiktok-account-1": {
                        "platform_post_id": "publish-123",
                        "status": "processing",
                    }
                },
            }
        return None

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        return SimpleNamespace(modified_count=1)


class FakeDB:
    def __init__(self):
        self.posts = FakePostsCollection()


@pytest.mark.asyncio
async def test_tiktok_webhook_completes_post_by_publish_id(monkeypatch):
    fake_db = FakeDB()
    finalize_mock = AsyncMock(return_value=("user-1", "processing", "published"))
    monkeypatch.setattr("celery_workers.tasks.publish._finalize_post_status", finalize_mock)

    await webhooks._process_tiktok_webhook(
        {
            "event": "post.publish.complete",
            "data": {"publish_id": "publish-123"},
        },
        fake_db,
    )

    assert fake_db.posts.update_calls
    _query, update = fake_db.posts.update_calls[0]
    set_fields = update["$set"]
    assert set_fields["platform_results.tiktok.status"] == "published"
    assert set_fields["account_results.tiktok-account-1.status"] == "published"
    finalize_mock.assert_awaited_once_with(fake_db, "post-1")
