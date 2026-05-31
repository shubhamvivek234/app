from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api.routes import accounts as accounts_route


class _FakeCursor:
    def __init__(self, docs):
        self._docs = [dict(doc) for doc in docs]

    async def to_list(self, length=None):
        if length is None:
            return list(self._docs)
        return list(self._docs)[:length]


class _FakeSocialAccountsCollection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]
        self.update_calls = []

    def find(self, query, _projection=None):
        matched = [
            dict(doc)
            for doc in self.docs
            if doc.get("user_id") == query.get("user_id")
            and doc.get("is_active", True) == query.get("is_active", True)
        ]
        return _FakeCursor(matched)

    async def find_one(self, query, _projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    async def update_one(self, query, update, upsert=False):
        self.update_calls.append((query, update, upsert))
        existing = await self.find_one(query, None)
        if existing is None and upsert:
            existing = {}
            self.docs.append(existing)
        if existing is None:
            return SimpleNamespace(modified_count=0)
        target_doc = next(doc for doc in self.docs if doc is existing or doc == existing)
        if "$set" in update:
            target_doc.update(update["$set"])
        return SimpleNamespace(modified_count=1)


class _FakeDB:
    def __init__(self, docs):
        self.social_accounts = _FakeSocialAccountsCollection(docs)


@pytest.mark.asyncio
async def test_list_accounts_exposes_account_level_publish_restriction_fields(monkeypatch):
    now = datetime.now(timezone.utc)
    db = _FakeDB([
        {
            "id": "tiktok-account-1",
            "account_id": "tiktok-account-1",
            "user_id": "user-1",
            "platform": "tiktok",
            "platform_user_id": "platform-user-1",
            "platform_username": "creator",
            "display_name": "Creator",
            "picture_url": "https://example.com/avatar.png",
            "is_active": True,
            "scopes": ["video.publish"],
            "connected_at": now,
            "publish_error_code": "unaudited_client_can_only_post_to_private_accounts",
            "publish_error_category": "provider_restriction",
            "publish_action_required": "complete_tiktok_audit_or_use_private_account",
            "publish_restriction_type": "tiktok_public_posting_not_approved",
            "publish_blocked_at": now,
        }
    ])

    responses = await accounts_route.list_accounts({"user_id": "user-1"}, db)

    assert len(responses) == 1
    response = responses[0]
    assert response.publish_error_code == "unaudited_client_can_only_post_to_private_accounts"
    assert response.publish_error_category == "provider_restriction"
    assert response.publish_action_required == "complete_tiktok_audit_or_use_private_account"
    assert response.publish_restriction_type == "tiktok_public_posting_not_approved"
    assert response.publish_blocked_at == now


@pytest.mark.asyncio
async def test_list_accounts_returns_null_publish_restriction_fields_when_not_blocked():
    now = datetime.now(timezone.utc)
    db = _FakeDB([
        {
            "id": "instagram-account-1",
            "account_id": "instagram-account-1",
            "user_id": "user-1",
            "platform": "instagram",
            "platform_user_id": "platform-user-1",
            "platform_username": "creator",
            "display_name": "Creator",
            "picture_url": "https://example.com/avatar.png",
            "is_active": True,
            "scopes": ["instagram_basic"],
            "connected_at": now,
        }
    ])

    responses = await accounts_route.list_accounts({"user_id": "user-1"}, db)

    assert len(responses) == 1
    response = responses[0]
    assert response.publish_error_code is None
    assert response.publish_error_category is None
    assert response.publish_action_required is None
    assert response.publish_restriction_type is None
    assert response.publish_blocked_at is None


@pytest.mark.asyncio
async def test_persist_oauth_account_clears_publish_restriction_fields(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(accounts_route, "encrypt", lambda value: f"enc:{value}")
    db = _FakeDB([
        {
            "id": "tiktok-account-1",
            "account_id": "tiktok-account-1",
            "user_id": "user-1",
            "platform": "tiktok",
            "platform_user_id": "platform-user-1",
            "is_active": True,
            "refresh_token": "encrypted-refresh",
            "publish_error_code": "unaudited_client_can_only_post_to_private_accounts",
            "publish_error_category": "provider_restriction",
            "publish_action_required": "complete_tiktok_audit_or_use_private_account",
            "publish_restriction_type": "tiktok_public_posting_not_approved",
            "publish_blocked_at": now,
        }
    ])

    account_id = await accounts_route._persist_oauth_account(
        db,
        "user-1",
        "tiktok",
        {
            "platform_user_id": "platform-user-1",
            "username": "creator",
            "display_name": "Creator",
            "picture_url": "https://example.com/avatar.png",
            "followers_count": 1,
            "following_count": 2,
            "posts_count": 3,
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "scopes": ["video.publish"],
            "expires_at": now,
        },
    )

    assert account_id.startswith("tiktok_user-1_")
    assert db.social_accounts.update_calls
    _query, update, upsert = db.social_accounts.update_calls[-1]
    assert upsert is True
    set_fields = update["$set"]
    assert set_fields["publish_error_code"] is None
    assert set_fields["publish_error_category"] is None
    assert set_fields["publish_action_required"] is None
    assert set_fields["publish_restriction_type"] is None
    assert set_fields["publish_blocked_at"] is None
