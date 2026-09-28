"""Mailbox settings API and background-task wiring fail closed."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_mailbox_settings_never_return_tokens_or_hunter_key():
    from outreach.api.mailboxes import list_mailboxes, hunter_key_status

    db = MagicMock()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[{
        "workspace_id": "ws", "sender_account_id": "sender", "email": "a@example.com",
        "provider": "gmail", "status": "active", "sync_status": "healthy",
        "access_token_enc": "secret", "refresh_token_enc": "secret",
    }])
    db.outreach_mailboxes.find.return_value = cursor
    db.outreach_hunter_credentials.find_one = AsyncMock(return_value={"api_key_enc": "secret"})
    user = {"user_id": "owner", "default_workspace_id": "ws"}

    mailboxes = await list_mailboxes(current_user=user, db=db)
    hunter = await hunter_key_status(current_user=user, db=db)

    assert mailboxes["mailboxes"][0]["email"] == "a@example.com"
    assert "secret" not in str(mailboxes)
    assert hunter["configured"] is True
    assert "secret" not in str(hunter)
    assert db.outreach_mailboxes.find.call_args.args[0] == {"workspace_id": "ws"}


@pytest.mark.asyncio
async def test_connection_job_lookup_is_workspace_scoped():
    from outreach.api.mailboxes import get_mailbox_connection_job

    db = MagicMock()
    db.outreach_mailbox_connection_jobs.find_one = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await get_mailbox_connection_job("job", current_user={"user_id": "owner", "default_workspace_id": "ws"}, db=db)
    assert exc.value.status_code == 404
    assert db.outreach_mailbox_connection_jobs.find_one.await_args.args[0] == {"workspace_id": "ws", "id": "job"}


@pytest.mark.asyncio
async def test_hunter_key_is_encrypted_and_never_echoed(monkeypatch):
    from outreach.api.mailboxes import HunterKeyRequest, put_hunter_key

    monkeypatch.setenv("OUTREACH_HUNTER_ENABLED", "true")
    db = MagicMock()
    db.outreach_hunter_credentials.update_one = AsyncMock()
    result = await put_hunter_key(HunterKeyRequest(api_key="hunter-private-key"), current_user={"user_id": "owner", "default_workspace_id": "ws"}, db=db)
    assert result == {"configured": True, "enabled": True}
    update = db.outreach_hunter_credentials.update_one.await_args.args[1]
    assert update["$set"]["api_key_enc"] != "hunter-private-key"
    assert "hunter-private-key" not in str(result)


def test_mailbox_worker_is_registered_and_scheduled():
    from celery_workers.celery_app import _SCHEDULE_MODULES, _TASK_MODULES, celery_app

    assert "celery_workers.tasks.mailbox" in _TASK_MODULES
    assert "celery_workers.tasks.mailbox" in _SCHEDULE_MODULES
    assert "sync-outreach-mailbox-replies" in celery_app.conf.beat_schedule


@pytest.mark.asyncio
async def test_mailbox_settings_require_an_active_workspace():
    from outreach.api.mailboxes import list_mailboxes

    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await list_mailboxes(current_user={"user_id": "owner"}, db=db)
    assert exc.value.status_code == 403
    db.outreach_mailboxes.find.assert_not_called()


@pytest.mark.asyncio
async def test_authorize_sets_http_only_initiator_cookie_without_echoing_secret():
    from fastapi import Response
    from outreach.api.mailboxes import AuthorizeMailboxRequest, authorize_mailbox

    response = Response()
    with patch("outreach.api.mailboxes.start_mailbox_connection", new_callable=AsyncMock,
               return_value={"authorization_url": "https://accounts.google.com/authorize",
                             "connection_job_id": "job", "browser_binding_cookie_name": "outreach_oauth_hash",
                             "browser_binding_nonce": "private-browser-nonce"}):
        payload = await authorize_mailbox(
            "gmail", AuthorizeMailboxRequest(sender_account_id="sender"), response,
            current_user={"user_id": "owner", "default_workspace_id": "ws"}, db=MagicMock(),
        )
    assert "private-browser-nonce" not in str(payload)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert "private-browser-nonce" in cookie
