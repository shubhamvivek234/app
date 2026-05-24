import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from celery_workers.tasks import publish as publish_tasks
from platform_adapters.base import ErrorClass, PlatformAPIError, classify_error


class FakePostsCollection:
    def __init__(self, post):
        self.post = dict(post)
        self.update_calls = []

    async def find_one(self, query, *_args, **_kwargs):
        if query.get("id") != self.post["id"]:
            return None
        return dict(self.post)

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        if "$set" in update:
            self.post.update(update["$set"])
        if "$push" in update:
            for key, value in update["$push"].items():
                self.post.setdefault(key, []).append(value)
        return SimpleNamespace(modified_count=1)


class FakeDB:
    def __init__(self, post):
        self.posts = FakePostsCollection(post)


class FakeClient:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, _name):
        return self._db


class RetryTriggered(Exception):
    def __init__(self, countdown):
        super().__init__(f"retry:{countdown}")
        self.countdown = countdown


@pytest.mark.asyncio
async def test_publish_post_dispatches_children_explicitly_and_records_task_ids(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    post = {
        "id": "post-1",
        "version": 1,
        "post_type": "video",
        "platforms": ["youtube", "linkedin"],
        "publish_targets": [
            {"platform": "youtube", "account_id": "youtube-account-1"},
            {"platform": "linkedin", "account_id": "linkedin-account-1"},
        ],
        "account_results": {
            "youtube-account-1": {"status": "pending"},
            "linkedin-account-1": {"status": "pending"},
        },
        "platform_results": {
            "youtube": {"status": "pending"},
            "linkedin": {"status": "pending"},
        },
        "status_history": [{"status": "queued", "timestamp": datetime.now(timezone.utc), "actor": "user"}],
    }
    fake_db = FakeDB(post)
    fake_task = SimpleNamespace(request=SimpleNamespace(id="parent-task-1"))

    monkeypatch.setattr(publish_tasks, "_check_poison_pill", AsyncMock(return_value=False))
    monkeypatch.setattr("celery_workers.shutdown_handler.is_shutting_down", Mock(return_value=False))
    monkeypatch.setattr(publish_tasks, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr(publish_tasks, "_jitter_seconds", Mock(return_value=0))

    child_results = [
        SimpleNamespace(id="child-youtube"),
        SimpleNamespace(id="fallback-youtube"),
        SimpleNamespace(id="child-linkedin"),
        SimpleNamespace(id="fallback-linkedin"),
    ]
    apply_async_mock = Mock(side_effect=child_results)
    monkeypatch.setattr(publish_tasks.publish_to_platform, "apply_async", apply_async_mock)

    result = await publish_tasks._async_publish_post(fake_task, "post-1", 1)

    assert result["status"] == "dispatched"
    assert [child["task_id"] for child in result["child_tasks"]] == ["child-youtube", "child-linkedin"]
    assert apply_async_mock.call_count == 4

    youtube_call = apply_async_mock.call_args_list[0]
    youtube_fallback_call = apply_async_mock.call_args_list[1]
    linkedin_call = apply_async_mock.call_args_list[2]
    linkedin_fallback_call = apply_async_mock.call_args_list[3]
    assert youtube_call.kwargs["queue"] == "publish_video"
    assert youtube_call.kwargs["kwargs"]["dispatch_source"] == "primary"
    assert youtube_call.kwargs["countdown"] == 0
    assert youtube_fallback_call.kwargs["queue"] == "default"
    assert youtube_fallback_call.kwargs["kwargs"]["dispatch_source"] == "fallback"
    assert youtube_fallback_call.kwargs["countdown"] == publish_tasks._PUBLISH_VIDEO_FALLBACK_DELAY_SECONDS
    assert linkedin_call.kwargs["queue"] == "publish_video"
    assert linkedin_call.kwargs["kwargs"]["dispatch_source"] == "primary"
    assert linkedin_call.kwargs["countdown"] == 0
    assert linkedin_fallback_call.kwargs["queue"] == "default"
    assert linkedin_fallback_call.kwargs["kwargs"]["dispatch_source"] == "fallback"
    assert linkedin_fallback_call.kwargs["countdown"] == publish_tasks._PUBLISH_VIDEO_FALLBACK_DELAY_SECONDS

    assert len(fake_db.posts.update_calls) == 2
    dispatch_update = fake_db.posts.update_calls[1][1]["$set"]
    assert dispatch_update["account_results.youtube-account-1.dispatch_task_id"] == "child-youtube"
    assert dispatch_update["account_results.linkedin-account-1.dispatch_task_id"] == "child-linkedin"
    assert dispatch_update["account_results.youtube-account-1.fallback_dispatch_task_id"] == "fallback-youtube"
    assert dispatch_update["account_results.linkedin-account-1.fallback_dispatch_task_id"] == "fallback-linkedin"
    assert dispatch_update["platform_results.youtube.dispatch_task_id"] == "child-youtube"
    assert dispatch_update["platform_results.linkedin.dispatch_task_id"] == "child-linkedin"


@pytest.mark.asyncio
async def test_publish_to_platform_clears_stale_lock_before_retrying(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc)
    post = {
        "id": "post-2",
        "user_id": "user-1",
        "status": "processing",
        "post_type": "video",
        "platforms": ["youtube"],
        "publish_targets": [
            {"platform": "youtube", "account_id": "youtube-account-1"},
        ],
        "account_results": {
            "youtube-account-1": {
                "status": "pending",
                "dispatch_enqueued_at": now - timedelta(seconds=180),
                "fallback_dispatch_enqueued_at": now - timedelta(seconds=170),
                "last_attempt_at": None,
                "dispatch_started_at": None,
            }
        },
        "platform_results": {
            "youtube": {
                "status": "pending",
                "dispatch_enqueued_at": now - timedelta(seconds=180),
                "fallback_dispatch_enqueued_at": now - timedelta(seconds=170),
                "last_attempt_at": None,
                "dispatch_started_at": None,
            }
        },
        "media_ids": [],
        "media_urls": ["https://example.com/video.mp4"],
        "media_url": "https://example.com/video.mp4",
    }
    fake_db = FakeDB(post)
    fake_task = SimpleNamespace(request=SimpleNamespace(id="child-task-1"))

    monkeypatch.setattr(publish_tasks, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr(publish_tasks, "get_cache_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "get_queue_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "safe_incr", AsyncMock(return_value=1))
    monkeypatch.setattr(publish_tasks, "safe_expire", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "safe_get", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "safe_setex", AsyncMock(return_value=True))
    safe_delete_mock = AsyncMock(return_value=1)
    monkeypatch.setattr(publish_tasks, "safe_delete", safe_delete_mock)
    acquire_lock_mock = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr(publish_tasks, "_acquire_publish_lock", acquire_lock_mock)
    monkeypatch.setattr(publish_tasks, "_release_publish_lock", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_requires_pre_upload", Mock(return_value=False))
    monkeypatch.setattr(publish_tasks, "_resolve_post_account", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_acquire_platform_slot", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "_release_platform_slot", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_finalize_post_status", AsyncMock(return_value=("user-1", "processing", "published")))
    monkeypatch.setattr(publish_tasks, "_send_success_notification", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_send_recovery_notification", AsyncMock(return_value=None))

    monkeypatch.setattr("utils.circuit_breaker.can_attempt", AsyncMock(return_value=True))
    monkeypatch.setattr("utils.circuit_breaker.record_success", AsyncMock(return_value=None))
    monkeypatch.setattr("utils.circuit_breaker.record_failure", AsyncMock(return_value=None))
    monkeypatch.setattr("utils.subscription.check_subscription_active", AsyncMock(return_value=(True, "active")))

    adapter = SimpleNamespace(publish=AsyncMock(return_value={"post_url": "https://youtube.example/post", "platform_post_id": "yt-post-1"}))
    monkeypatch.setattr("platform_adapters.get_adapter", Mock(return_value=adapter))

    result = await publish_tasks._async_publish_to_platform(
        fake_task,
        "post-2",
        "youtube",
        "youtube-account-1",
        0,
        "fallback",
    )

    assert result["status"] == "published"
    assert acquire_lock_mock.await_count == 2
    safe_delete_mock.assert_awaited_once()
    assert any(
        "$set" in update and update["$set"].get("account_results.youtube-account-1.status") == "processing"
        for _query, update in fake_db.posts.update_calls
    )


def test_classify_error_treats_platform_api_429_as_rate_limited():
    exc = PlatformAPIError("Rate limited — requeue", code=429, retry_after=120)
    assert classify_error(exc, "youtube") == ErrorClass.RATE_LIMITED


@pytest.mark.asyncio
async def test_async_pre_upload_marks_retryable_rate_limit_as_retrying(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    post = {
        "id": "post-3",
        "user_id": "user-1",
        "status": "processing",
        "post_type": "video",
        "platforms": ["youtube"],
        "publish_targets": [{"platform": "youtube", "account_id": "youtube-account-1"}],
    }
    fake_db = FakeDB(post)

    def _raise_retry(**kwargs):
        raise RetryTriggered(kwargs["countdown"])

    fake_task = SimpleNamespace(
        request=SimpleNamespace(id="preupload-task-1"),
        retry=Mock(side_effect=_raise_retry),
    )

    monkeypatch.setattr(publish_tasks, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr(publish_tasks, "get_cache_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "_acquire_pre_upload_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "_release_pre_upload_lock", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_hydrate_post_media", AsyncMock(side_effect=lambda _db, current: current))
    monkeypatch.setattr(
        publish_tasks,
        "_resolve_post_account",
        AsyncMock(return_value={"id": "youtube-account-1", "access_token": "encrypted"}),
    )
    monkeypatch.setattr(publish_tasks, "_sync_pre_upload_aggregate", AsyncMock(return_value=None))

    adapter = SimpleNamespace(
        pre_upload=AsyncMock(side_effect=PlatformAPIError("Rate limited — requeue", code=429, retry_after=600))
    )
    monkeypatch.setattr("platform_adapters.get_adapter", Mock(return_value=adapter))

    with pytest.raises(RetryTriggered) as exc_info:
        await publish_tasks._async_pre_upload(fake_task, "post-3", "youtube", "youtube-account-1")

    assert exc_info.value.countdown == 600
    final_update = fake_db.posts.update_calls[-1][1]
    assert final_update["$set"]["pre_upload_results.youtube-account-1.status"] == "retrying"
    assert "pre_upload_results.youtube-account-1.next_retry_at" in final_update["$set"]
    assert "pre_upload_results.youtube-account-1.completed_at" in final_update["$unset"]
    assert "pre_upload_results.youtube-account-1.actual_duration_secs" in final_update["$unset"]


@pytest.mark.asyncio
async def test_publish_to_platform_waits_for_existing_pre_upload_retry(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc)
    post = {
        "id": "post-4",
        "user_id": "user-1",
        "status": "processing",
        "post_type": "video",
        "platforms": ["youtube"],
        "media_urls": ["https://example.com/video.mp4"],
        "media_url": "https://example.com/video.mp4",
        "publish_targets": [{"platform": "youtube", "account_id": "youtube-account-1"}],
        "pre_upload_results": {
            "youtube-account-1": {
                "status": "retrying",
                "error": "Rate limited — requeue",
                "next_retry_at": now + timedelta(minutes=10),
            }
        },
        "account_results": {
            "youtube-account-1": {
                "status": "pending",
                "dispatch_enqueued_at": now - timedelta(seconds=10),
            }
        },
        "platform_results": {"youtube": {"status": "pending"}},
    }
    fake_db = FakeDB(post)

    def _raise_retry(**kwargs):
        raise RetryTriggered(kwargs["countdown"])

    fake_task = SimpleNamespace(
        request=SimpleNamespace(id="publish-task-2"),
        retry=Mock(side_effect=_raise_retry),
    )

    monkeypatch.setattr(publish_tasks, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr(publish_tasks, "get_cache_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "get_queue_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "safe_incr", AsyncMock(return_value=1))
    monkeypatch.setattr(publish_tasks, "safe_expire", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "safe_get", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "safe_setex", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "_acquire_publish_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "_release_publish_lock", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_hydrate_post_media", AsyncMock(side_effect=lambda _db, current: current))
    monkeypatch.setattr(publish_tasks, "_resolve_post_account", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_async_pre_upload", AsyncMock(return_value={"status": "should_not_run"}))
    monkeypatch.setattr("utils.circuit_breaker.can_attempt", AsyncMock(return_value=True))

    with pytest.raises(RetryTriggered) as exc_info:
        await publish_tasks._async_publish_to_platform(
            fake_task,
            "post-4",
            "youtube",
            "youtube-account-1",
            0,
            "fallback",
        )

    assert exc_info.value.countdown >= 540
    publish_tasks._async_pre_upload.assert_not_awaited()
