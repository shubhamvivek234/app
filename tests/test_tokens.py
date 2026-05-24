from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from celery_workers.tasks import tokens


class _FakeSocialAccounts:
    def __init__(self, account):
        self.account = account
        self.update_calls = []

    async def find_one(self, *_args, **_kwargs):
        return self.account

    async def update_one(self, query, update):
        self.update_calls.append((query, update))
        return SimpleNamespace(modified_count=1)


class _FakeDB:
    def __init__(self, account):
        self.social_accounts = _FakeSocialAccounts(account)


@asynccontextmanager
async def _noop_lock(*_args, **_kwargs):
    yield


@pytest.mark.asyncio
async def test_refresh_with_lock_skips_recently_refreshed_naive_expiry(monkeypatch):
    future_expiry = datetime.now() + timedelta(days=10)
    fake_db = _FakeDB(
        {
            "token_expiry": future_expiry,
            "refresh_token": "enc-refresh",
            "access_token": "enc-access",
        }
    )

    monkeypatch.setattr("db.redis_client.get_cache_redis", lambda: object())
    monkeypatch.setattr(tokens, "best_effort_lock", _noop_lock)

    await tokens._refresh_with_lock(fake_db, "acct-1", "youtube")

    assert fake_db.social_accounts.update_calls == []


@pytest.mark.asyncio
async def test_refresh_with_lock_refreshes_expired_naive_expiry(monkeypatch):
    stale_expiry = datetime.now() - timedelta(days=1)
    fake_db = _FakeDB(
        {
            "token_expiry": stale_expiry,
            "refresh_token": "enc-refresh",
            "access_token": "enc-access",
        }
    )

    refresh_mock = AsyncMock(
        return_value={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        }
    )
    fake_adapter = SimpleNamespace(refresh_token=refresh_mock)

    monkeypatch.setattr("db.redis_client.get_cache_redis", lambda: object())
    monkeypatch.setattr(tokens, "best_effort_lock", _noop_lock)
    monkeypatch.setattr(tokens, "decrypt", lambda value: value)
    monkeypatch.setattr(tokens, "encrypt", lambda value: f"enc:{value}")
    monkeypatch.setattr("platform_adapters.get_adapter", lambda _platform: fake_adapter)

    await tokens._refresh_with_lock(fake_db, "acct-1", "youtube")

    refresh_mock.assert_awaited_once_with("enc-refresh")
    assert len(fake_db.social_accounts.update_calls) == 1
    _query, update = fake_db.social_accounts.update_calls[0]
    assert update["$set"]["access_token"] == "enc:new-access"
    assert update["$set"]["refresh_token"] == "enc:new-refresh"
