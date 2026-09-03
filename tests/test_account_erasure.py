import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from starlette.requests import Request

from api.routes.user import delete_account
from celery_workers.tasks.gdpr import _async_erase


@pytest.mark.asyncio
async def test_delete_account_endpoint_queues_erasure():
    import uuid
    scope = {
        "type": "http",
        "method": "DELETE",
        "path": "/api/user/account",
        "client": (f"10.99.{uuid.uuid4().hex[:2]}.{uuid.uuid4().hex[:2]}", 12345),
        "headers": [],
    }
    req = Request(scope=scope)

    current_user = {
        "user_id": "usr_test_12345",
        "default_workspace_id": "ws_test_abcde",
        "firebase_uid": "fb_uid_9999",
        "status": "active",
    }

    db = MagicMock()
    db.users.update_one = AsyncMock()

    with patch("api.routes.user.enqueue_task") as mock_enqueue:
        response = await delete_account(request=req, current_user=current_user, db=db)

        db.users.update_one.assert_awaited_once()
        filter_arg, update_arg = db.users.update_one.call_args[0]
        assert filter_arg == {"user_id": "usr_test_12345"}
        assert update_arg["$set"]["status"] == "deletion_pending"

        mock_enqueue.assert_called_once_with(
            "celery_workers.tasks.gdpr.process_erasure_request",
            kwargs={
                "user_id": "usr_test_12345",
                "workspace_id": "ws_test_abcde",
                "firebase_uid": "fb_uid_9999",
            },
            queue="default",
        )

        assert response.status == "queued"
        assert "30 days" in response.message


@pytest.mark.asyncio
async def test_api_deps_blocks_deletion_pending_user():
    from api.deps import get_current_user

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/posts",
        "client": ("127.0.0.1", 12345),
        "headers": [],
    }
    req = Request(scope=scope)

    pending_user = {
        "user_id": "usr_pending_123",
        "status": "deletion_pending",
        "default_workspace_id": "ws_123",
    }

    db = MagicMock()

    with patch("api.deps.get_firebase_app"):
        with patch("api.deps.verify_session_cookie", new=AsyncMock(return_value={"uid": "fb_uid_123"})):
            with patch("api.deps._bootstrap_user_from_claims", new=AsyncMock(return_value=pending_user)):
                with patch("api.deps.ensure_active_workspace", new=AsyncMock(return_value=pending_user)):
                    req._cookies = {"session": "valid_session_cookie"}
                    with pytest.raises(HTTPException) as exc_info:
                        await get_current_user(request=req, credentials=None, db=db)

                    assert exc_info.value.status_code == 403
                    assert "permanent deletion" in exc_info.value.detail


@pytest.mark.asyncio
async def test_async_erase_cascades_all_collections_and_storage():
    mock_db = MagicMock()
    mock_client = {
        "test_socialentangler": mock_db
    }

    collections = {}
    for col in [
        "posts", "social_accounts", "analytics", "login_events",
        "webhook_endpoints", "bulk_imports", "notifications",
        "inbox_messages", "api_keys", "short_links", "short_link_clicks",
        "utm_presets", "bio_pages", "bio_analytics", "workspace_leads",
        "user_sessions", "reports", "media_assets", "workspaces",
    ]:
        col_mock = MagicMock(delete_many=AsyncMock(return_value=MagicMock(deleted_count=2)))
        setattr(mock_db, col, col_mock)
        collections[col] = col_mock

    mock_db.__getitem__.side_effect = lambda key: collections.get(key, MagicMock(delete_many=AsyncMock(return_value=MagicMock(deleted_count=0))))

    mock_db.workspace_members = MagicMock(update_many=AsyncMock(return_value=MagicMock(modified_count=1)))
    mock_db.users = MagicMock(
        find_one=AsyncMock(return_value={
            "user_id": "usr_wipe_me",
            "firebase_uid": "fb_wipe_uid",
            "stripe_subscription_id": None,
            "razorpay_subscription_id": None,
        }),
        delete_one=AsyncMock(return_value=MagicMock(deleted_count=1)),
    )
    mock_db.audit_events = MagicMock(insert_one=AsyncMock())

    class AsyncCursor:
        def __init__(self, items):
            self._items = items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)

    mock_db.media_assets.find = MagicMock(return_value=AsyncCursor([
        {"url": "https://r2.unravler.com/uploads/photo1.jpg"},
        {"url": "https://r2.unravler.com/uploads/video1.mp4"},
    ]))

    with patch.dict("os.environ", {"DB_NAME": "test_socialentangler"}):
        with patch("celery_workers.tasks.gdpr.get_client", new=AsyncMock(return_value=mock_client)):
            with patch("utils.storage.delete_file_async", new=AsyncMock()) as mock_del_file:
                with patch("firebase_admin.auth.delete_user") as mock_fb_delete:
                    with patch("api.deps.get_firebase_app"):
                        result = await _async_erase(
                            user_id="usr_wipe_me",
                            workspace_id="ws_wipe_me",
                            firebase_uid="fb_wipe_uid",
                        )

                        assert result["status"] == "completed"
                        assert mock_del_file.await_count == 2
                        assert result["deleted"]["storage_files_deleted"] == 2
                        assert result["deleted"]["users_deleted"] == 1
                        mock_db.users.delete_one.assert_awaited_once_with({"user_id": "usr_wipe_me"})
                        mock_fb_delete.assert_called_once_with("fb_wipe_uid")
                        mock_db.audit_events.insert_one.assert_awaited_once()
