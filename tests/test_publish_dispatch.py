import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from celery_workers.tasks import publish as publish_tasks
from platform_adapters.base import ErrorClass, PlatformAPIError, PlatformHTTPError, classify_error


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


class FakeSocialAccountsCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]
        self.update_calls = []

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs:
            if query.get("platform") and doc.get("platform") != query.get("platform"):
                continue
            or_conditions = query.get("$or") or []
            if or_conditions:
                if any(
                    all(doc.get(key) == value for key, value in condition.items())
                    for condition in or_conditions
                ):
                    return dict(doc)
            elif all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        target = await self.find_one(query)
        if target is None:
            return SimpleNamespace(modified_count=0)
        for doc in self.docs:
            if doc.get("platform") != target.get("platform"):
                continue
            if doc.get("account_id") == target.get("account_id") or doc.get("id") == target.get("id"):
                if "$set" in update:
                    doc.update(update["$set"])
                break
        return SimpleNamespace(modified_count=1)


class FakeDB:
    def __init__(self, post, social_accounts=None):
        self.posts = FakePostsCollection(post)
        self.social_accounts = FakeSocialAccountsCollection(social_accounts)


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
    monkeypatch.setitem(__import__("utils.feature_flags", fromlist=["_ENV_DEFAULTS"])._ENV_DEFAULTS, "tiktok_publishing", True)
    monkeypatch.setattr("utils.feature_flags.is_enabled", Mock(return_value=True))

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


def test_get_platform_pre_upload_status_does_not_fall_back_to_stale_aggregate_status():
    post = {
        "pre_upload_status": "pending",
        "pre_upload_results": {
            "youtube-account-1": {},
        },
    }

    assert publish_tasks._get_platform_pre_upload_status(post, "youtube-account-1") is None


def test_is_auth_error_excludes_tiktok_unaudited_private_account_restriction():
    exc = PlatformHTTPError(
        403,
        '{"error":{"code":"unaudited_client_can_only_post_to_private_accounts","message":"Please review our integration guidelines"}}',
    )

    assert publish_tasks._is_auth_error("tiktok", exc) is False


def test_provider_restriction_metadata_maps_tiktok_public_posting_gate():
    exc = PlatformHTTPError(
        403,
        "TikTok rejected the post",
        code="unaudited_client_can_only_post_to_private_accounts",
    )

    metadata = publish_tasks._get_provider_restriction_metadata("tiktok", exc)

    assert metadata == {
        "error_code": "unaudited_client_can_only_post_to_private_accounts",
        "error_category": "provider_restriction",
        "action_required": "complete_tiktok_audit_or_use_private_account",
        "restriction_type": "tiktok_public_posting_not_approved",
    }


@pytest.mark.asyncio
async def test_finalize_post_status_updates_timestamp_and_history_on_terminal_transition(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc)
    post = {
        "id": "post-finalize-1",
        "user_id": "user-1",
        "status": "processing",
        "post_type": "video",
        "platforms": ["tiktok"],
        "account_results": {
            "tiktok-account-1": {
                "status": "failed",
                "error": "provider rejected post",
            }
        },
        "platform_results": {
            "tiktok": {
                "status": "processing",
            }
        },
        "status_history": [
            {"status": "processing", "timestamp": now - timedelta(minutes=1), "actor": "celery_publish_parent"}
        ],
        "updated_at": now - timedelta(minutes=1),
    }
    fake_db = FakeDB(post)

    cleanup_apply_async = Mock()
    monkeypatch.setattr(
        "celery_workers.tasks.cleanup.schedule_media_cleanup",
        SimpleNamespace(apply_async=cleanup_apply_async),
    )

    user_id, prev_status, agg_status = await publish_tasks._finalize_post_status(fake_db, "post-finalize-1")

    assert (user_id, prev_status, agg_status) == ("user-1", "processing", "failed")
    assert fake_db.posts.update_calls
    update = fake_db.posts.update_calls[0][1]
    assert "updated_at" in update["$set"]
    assert update["$set"]["status"] == "failed"
    assert update["$push"]["status_history"]["status"] == "failed"
    assert update["$push"]["status_history"]["actor"] == "celery_finalize"
    cleanup_apply_async.assert_called_once()


@pytest.mark.asyncio
async def test_tiktok_public_posting_restriction_marks_structured_failure_without_reauth(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc)
    post = {
        "id": "post-tiktok-restriction-1",
        "user_id": "user-1",
        "status": "processing",
        "post_type": "video",
        "platforms": ["tiktok"],
        "publish_targets": [{"platform": "tiktok", "account_id": "tiktok-account-1"}],
        "account_results": {
            "tiktok-account-1": {"status": "pending"},
        },
        "platform_results": {
            "tiktok": {"status": "pending"},
        },
        "media_ids": [],
        "media_urls": ["https://example.com/video.mp4"],
        "media_url": "https://example.com/video.mp4",
        "created_at": now,
        "updated_at": now,
    }
    fake_db = FakeDB(
        post,
        social_accounts=[
            {
                "id": "tiktok-account-1",
                "account_id": "tiktok-account-1",
                "platform": "tiktok",
                "user_id": "user-1",
                "publish_error_code": None,
                "publish_error_category": None,
                "publish_action_required": None,
                "publish_restriction_type": None,
                "publish_blocked_at": None,
            }
        ],
    )
    fake_task = SimpleNamespace(request=SimpleNamespace(id="child-task-tiktok-restriction"))

    monkeypatch.setattr(publish_tasks, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr(publish_tasks, "get_cache_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "get_queue_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "safe_incr", AsyncMock(return_value=1))
    monkeypatch.setattr(publish_tasks, "safe_expire", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "safe_get", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "safe_setex", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "safe_delete", AsyncMock(return_value=1))
    monkeypatch.setattr(publish_tasks, "_acquire_publish_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "_release_publish_lock", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_requires_pre_upload", Mock(return_value=False))
    monkeypatch.setattr(publish_tasks, "_resolve_post_account", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_acquire_platform_slot", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "_release_platform_slot", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_finalize_post_status", AsyncMock(return_value=("user-1", "processing", "failed")))
    monkeypatch.setattr(publish_tasks, "_send_failure_notification", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_send_recovery_notification", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_send_success_notification", AsyncMock(return_value=None))
    monkeypatch.setattr("utils.circuit_breaker.can_attempt", AsyncMock(return_value=True))
    monkeypatch.setattr("utils.circuit_breaker.record_success", AsyncMock(return_value=None))
    record_failure_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(publish_tasks, "record_failure", record_failure_mock)
    monkeypatch.setattr("utils.subscription.check_subscription_active", AsyncMock(return_value=(True, "active")))
    monkeypatch.setitem(__import__("utils.feature_flags", fromlist=["_ENV_DEFAULTS"])._ENV_DEFAULTS, "tiktok_publishing", True)
    monkeypatch.setattr("utils.feature_flags.is_enabled", Mock(return_value=True))

    apply_async_mock = Mock()
    monkeypatch.setattr(publish_tasks.publish_to_platform, "apply_async", apply_async_mock)

    adapter = SimpleNamespace(
        publish=AsyncMock(
            side_effect=PlatformHTTPError(
                403,
                "TikTok rejected the post",
                code="unaudited_client_can_only_post_to_private_accounts",
            )
        )
    )
    monkeypatch.setattr("platform_adapters.get_adapter", Mock(return_value=adapter))

    result = await publish_tasks._async_publish_to_platform(
        fake_task,
        "post-tiktok-restriction-1",
        "tiktok",
        "tiktok-account-1",
        0,
        "primary",
    )

    assert result["status"] == "permanent_failure"
    assert apply_async_mock.call_count == 0
    record_failure_mock.assert_awaited_once()
    assert any(
        "$set" in update
        and update["$set"].get("account_results.tiktok-account-1.error_code") == "unaudited_client_can_only_post_to_private_accounts"
        and update["$set"].get("account_results.tiktok-account-1.error_category") == "provider_restriction"
        and update["$set"].get("account_results.tiktok-account-1.action_required") == "complete_tiktok_audit_or_use_private_account"
        and update["$set"].get("account_results.tiktok-account-1.restriction_type") == "tiktok_public_posting_not_approved"
        for _query, update in fake_db.posts.update_calls
    )
    assert any(
        "$set" in update
        and update["$set"].get("publish_error_code") == "unaudited_client_can_only_post_to_private_accounts"
        and update["$set"].get("publish_error_category") == "provider_restriction"
        and update["$set"].get("publish_action_required") == "complete_tiktok_audit_or_use_private_account"
        and update["$set"].get("publish_restriction_type") == "tiktok_public_posting_not_approved"
        and update["$set"].get("publish_blocked_at") is not None
        for _query, update in fake_db.social_accounts.update_calls
    )


@pytest.mark.asyncio
async def test_publish_to_platform_skips_fallback_when_target_already_terminal(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    post = {
        "id": "post-fallback-terminal-1",
        "user_id": "user-1",
        "status": "failed",
        "post_type": "video",
        "platforms": ["tiktok"],
        "publish_targets": [{"platform": "tiktok", "account_id": "tiktok-account-1"}],
        "account_results": {
            "tiktok-account-1": {
                "status": "failed",
                "error": "Access token invalid",
                "error_code": "access_token_invalid",
            },
        },
        "platform_results": {
            "tiktok": {
                "status": "failed",
                "error": "Access token invalid",
            },
        },
        "media_ids": [],
        "media_urls": ["https://example.com/video.mp4"],
        "media_url": "https://example.com/video.mp4",
    }
    fake_db = FakeDB(post)
    fake_task = SimpleNamespace(request=SimpleNamespace(id="child-task-fallback-terminal"))

    monkeypatch.setattr(publish_tasks, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr(publish_tasks, "get_cache_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "get_queue_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "safe_incr", AsyncMock(return_value=1))
    monkeypatch.setattr(publish_tasks, "safe_expire", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "safe_get", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_hydrate_post_media", AsyncMock(side_effect=lambda _db, current: current))
    monkeypatch.setitem(__import__("utils.feature_flags", fromlist=["_ENV_DEFAULTS"])._ENV_DEFAULTS, "tiktok_publishing", True)
    adapter = SimpleNamespace(publish=AsyncMock())
    get_adapter_mock = Mock(return_value=adapter)
    monkeypatch.setattr("platform_adapters.get_adapter", get_adapter_mock)

    result = await publish_tasks._async_publish_to_platform(
        fake_task,
        "post-fallback-terminal-1",
        "tiktok",
        "tiktok-account-1",
        0,
        "fallback",
    )

    assert result == {
        "status": "already_terminal",
        "platform": "tiktok",
        "account_id": "tiktok-account-1",
        "current_status": "failed",
    }
    assert fake_db.posts.update_calls == []
    get_adapter_mock.assert_not_called()
    adapter.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_to_platform_preserves_async_processing_status(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    post = {
        "id": "post-async-1",
        "user_id": "user-1",
        "status": "processing",
        "post_type": "video",
        "platforms": ["tiktok"],
        "publish_targets": [
            {"platform": "tiktok", "account_id": "tiktok-account-1"},
        ],
        "account_results": {
            "tiktok-account-1": {"status": "pending"},
        },
        "platform_results": {
            "tiktok": {"status": "pending"},
        },
        "media_ids": [],
        "media_urls": ["https://example.com/video.mp4"],
        "media_url": "https://example.com/video.mp4",
    }
    fake_db = FakeDB(post)
    fake_task = SimpleNamespace(request=SimpleNamespace(id="child-task-async"))

    monkeypatch.setattr(publish_tasks, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr(publish_tasks, "get_cache_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "get_queue_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "safe_incr", AsyncMock(return_value=1))
    monkeypatch.setattr(publish_tasks, "safe_expire", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "safe_get", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "safe_setex", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "safe_delete", AsyncMock(return_value=1))
    monkeypatch.setattr(publish_tasks, "_acquire_publish_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "_release_publish_lock", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_requires_pre_upload", Mock(return_value=False))
    monkeypatch.setattr(publish_tasks, "_resolve_post_account", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_acquire_platform_slot", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "_release_platform_slot", AsyncMock(return_value=None))
    finalize_mock = AsyncMock(return_value=("user-1", "processing", "processing"))
    monkeypatch.setattr(publish_tasks, "_finalize_post_status", finalize_mock)
    monkeypatch.setattr(publish_tasks, "_send_success_notification", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "_send_recovery_notification", AsyncMock(return_value=None))

    monkeypatch.setattr("utils.circuit_breaker.can_attempt", AsyncMock(return_value=True))
    monkeypatch.setattr("utils.circuit_breaker.record_success", AsyncMock(return_value=None))
    monkeypatch.setattr("utils.circuit_breaker.record_failure", AsyncMock(return_value=None))
    monkeypatch.setattr("utils.subscription.check_subscription_active", AsyncMock(return_value=(True, "active")))
    monkeypatch.setitem(__import__("utils.feature_flags", fromlist=["_ENV_DEFAULTS"])._ENV_DEFAULTS, "tiktok_publishing", True)

    adapter = SimpleNamespace(
        publish=AsyncMock(
            return_value={
                "status": "processing",
                "post_url": "",
                "platform_post_id": "tiktok-publish-1",
            }
        )
    )
    monkeypatch.setattr("platform_adapters.get_adapter", Mock(return_value=adapter))

    result = await publish_tasks._async_publish_to_platform(
        fake_task,
        "post-async-1",
        "tiktok",
        "tiktok-account-1",
        0,
        "primary",
    )

    assert result["status"] == "processing"
    finalize_mock.assert_awaited_once()
    assert any(
        "$set" in update and update["$set"].get("account_results.tiktok-account-1.provider_status") == "processing"
        for _query, update in fake_db.posts.update_calls
    )


@pytest.mark.asyncio
async def test_publish_to_platform_clears_account_publish_restriction_after_success(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    post = {
        "id": "post-tiktok-success-1",
        "user_id": "user-1",
        "status": "processing",
        "post_type": "video",
        "platforms": ["tiktok"],
        "publish_targets": [
            {"platform": "tiktok", "account_id": "tiktok-account-1"},
        ],
        "account_results": {
            "tiktok-account-1": {"status": "pending"},
        },
        "platform_results": {
            "tiktok": {"status": "pending"},
        },
        "media_ids": [],
        "media_urls": ["https://example.com/video.mp4"],
        "media_url": "https://example.com/video.mp4",
    }
    fake_db = FakeDB(
        post,
        social_accounts=[
            {
                "id": "tiktok-account-1",
                "account_id": "tiktok-account-1",
                "platform": "tiktok",
                "user_id": "user-1",
                "publish_error_code": "unaudited_client_can_only_post_to_private_accounts",
                "publish_error_category": "provider_restriction",
                "publish_action_required": "complete_tiktok_audit_or_use_private_account",
                "publish_restriction_type": "tiktok_public_posting_not_approved",
                "publish_blocked_at": datetime.now(timezone.utc),
            }
        ],
    )
    fake_task = SimpleNamespace(request=SimpleNamespace(id="child-task-tiktok-success"))

    monkeypatch.setattr(publish_tasks, "get_client", AsyncMock(return_value=FakeClient(fake_db)))
    monkeypatch.setattr(publish_tasks, "get_cache_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "get_queue_redis", Mock(return_value=object()))
    monkeypatch.setattr(publish_tasks, "safe_incr", AsyncMock(return_value=1))
    monkeypatch.setattr(publish_tasks, "safe_expire", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "safe_get", AsyncMock(return_value=None))
    monkeypatch.setattr(publish_tasks, "safe_setex", AsyncMock(return_value=True))
    monkeypatch.setattr(publish_tasks, "safe_delete", AsyncMock(return_value=1))
    monkeypatch.setattr(publish_tasks, "_acquire_publish_lock", AsyncMock(return_value=True))
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
    monkeypatch.setitem(__import__("utils.feature_flags", fromlist=["_ENV_DEFAULTS"])._ENV_DEFAULTS, "tiktok_publishing", True)
    monkeypatch.setattr("utils.feature_flags.is_enabled", Mock(return_value=True))

    adapter = SimpleNamespace(
        publish=AsyncMock(
            return_value={
                "status": "published",
                "post_url": "https://tiktok.example/post/1",
                "platform_post_id": "publish-1",
            }
        )
    )
    monkeypatch.setattr("platform_adapters.get_adapter", Mock(return_value=adapter))

    result = await publish_tasks._async_publish_to_platform(
        fake_task,
        "post-tiktok-success-1",
        "tiktok",
        "tiktok-account-1",
        0,
        "primary",
    )

    assert result["status"] == "published"
    assert any(
        "$set" in update
        and update["$set"].get("publish_error_code") is None
        and update["$set"].get("publish_error_category") is None
        and update["$set"].get("publish_action_required") is None
        and update["$set"].get("publish_restriction_type") is None
        and update["$set"].get("publish_blocked_at") is None
        for _query, update in fake_db.social_accounts.update_calls
    )


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


@pytest.mark.asyncio
async def test_publish_to_platform_refreshes_token_when_pre_upload_auth_fails(monkeypatch):
    os.environ["DB_NAME"] = "testdb"
    now = datetime.now(timezone.utc)
    post = {
        "id": "post-5",
        "user_id": "user-1",
        "status": "processing",
        "post_type": "video",
        "platforms": ["youtube"],
        "media_urls": ["https://example.com/video.mp4"],
        "media_url": "https://example.com/video.mp4",
        "publish_targets": [{"platform": "youtube", "account_id": "youtube-account-1"}],
        "account_results": {
            "youtube-account-1": {
                "status": "pending",
                "dispatch_enqueued_at": now - timedelta(seconds=10),
            }
        },
        "platform_results": {"youtube": {"status": "pending"}},
    }
    fake_db = FakeDB(post)
    fake_task = SimpleNamespace(request=SimpleNamespace(id="publish-task-3"))

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
    monkeypatch.setattr("utils.circuit_breaker.can_attempt", AsyncMock(return_value=True))
    monkeypatch.setattr("utils.subscription.check_subscription_active", AsyncMock(return_value=(True, "active")))

    pre_upload_exc = PlatformHTTPError(401, "Invalid Credentials")
    monkeypatch.setattr(publish_tasks, "_async_pre_upload", AsyncMock(side_effect=pre_upload_exc))
    refresh_mock = AsyncMock(return_value=None)
    monkeypatch.setattr("celery_workers.tasks.tokens._refresh_with_lock", refresh_mock)
    apply_async_mock = Mock(return_value=SimpleNamespace(id="requeued-after-refresh"))
    monkeypatch.setattr(publish_tasks.publish_to_platform, "apply_async", apply_async_mock)
    monkeypatch.setattr(publish_tasks, "_sync_pre_upload_aggregate", AsyncMock(return_value=None))

    result = await publish_tasks._async_publish_to_platform(
        fake_task,
        "post-5",
        "youtube",
        "youtube-account-1",
        0,
        "primary",
    )

    assert result["status"] == "token_refreshed_requeued"
    refresh_mock.assert_awaited_once_with(fake_db, "youtube-account-1", "youtube")
    assert apply_async_mock.call_count == 1
    requeue_kwargs = apply_async_mock.call_args.kwargs["kwargs"]
    assert requeue_kwargs["attempt"] == 1
    assert requeue_kwargs["account_id"] == "youtube-account-1"
    assert requeue_kwargs["dispatch_source"] == "primary"
    reset_update = fake_db.posts.update_calls[-1][1]
    assert reset_update["$set"]["updated_at"] is not None
    assert "pre_upload_results.youtube-account-1.status" not in reset_update["$set"]
    assert "pre_upload_results.youtube-account-1.status" in reset_update["$unset"]
    assert "pre_upload_results.youtube-account-1.started_at" in reset_update["$unset"]
    assert "pre_upload_results.youtube-account-1.next_retry_at" in reset_update["$unset"]
