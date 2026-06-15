import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from api.routes import accounts as accounts_route
from backend.app.social import linkedin as linkedin_module


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

    def _matches(self, doc, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self._matches(doc, condition) for condition in value):
                    return False
                continue
            if isinstance(value, dict) and "$exists" in value:
                exists = key in doc
                if bool(value["$exists"]) != exists:
                    return False
                continue
            if doc.get(key) != value:
                return False
        return True

    def find(self, query, _projection=None):
        matched = [
            dict(doc)
            for doc in self.docs
            if self._matches(doc, query)
        ]
        return _FakeCursor(matched)

    async def find_one(self, query, _projection=None):
        for doc in self.docs:
            if self._matches(doc, query):
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
    assert response.connection_state == "restricted"
    assert response.connection_message == "complete_tiktok_audit_or_use_private_account"
    assert response.requires_reconnect is False


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
    assert response.connection_state == "healthy"
    assert response.connection_message == "Connection is healthy."
    assert response.requires_reconnect is False


@pytest.mark.asyncio
async def test_list_accounts_marks_non_refreshable_expired_accounts_for_reconnect():
    now = datetime.now(timezone.utc)
    db = _FakeDB([
        {
            "id": "facebook-account-1",
            "account_id": "facebook-account-1",
            "user_id": "user-1",
            "platform": "facebook",
            "platform_user_id": "platform-user-1",
            "platform_username": "creator",
            "display_name": "Creator",
            "picture_url": "https://example.com/avatar.png",
            "is_active": True,
            "scopes": ["pages_manage_posts"],
            "connected_at": now,
            "expires_at": now - timedelta(days=365),
        }
    ])

    responses = await accounts_route.list_accounts({"user_id": "user-1"}, db)

    assert len(responses) == 1
    response = responses[0]
    assert response.connection_state == "reconnect_required"
    assert response.requires_reconnect is True
    assert response.reconnect_reason == "Access token expired."
    assert response.reconnect_required_at == response.expires_at


@pytest.mark.asyncio
async def test_list_accounts_keeps_expired_refreshable_accounts_healthy():
    now = datetime.now(timezone.utc)
    db = _FakeDB([
        {
            "id": "youtube-account-1",
            "account_id": "youtube-account-1",
            "user_id": "user-1",
            "platform": "youtube",
            "platform_user_id": "UC123",
            "platform_username": "Creator",
            "display_name": "Creator",
            "picture_url": "https://example.com/avatar.png",
            "is_active": True,
            "scopes": ["youtube.upload"],
            "connected_at": now,
            "expires_at": now - timedelta(days=365),
            "refresh_token": "encrypted-refresh-token",
        }
    ])

    responses = await accounts_route.list_accounts({"user_id": "user-1"}, db)

    assert len(responses) == 1
    response = responses[0]
    assert response.connection_state == "healthy"
    assert response.connection_message == "Connection is healthy."
    assert response.requires_reconnect is False


def test_account_connection_routes_allow_authenticated_unverified_users():
    assert inspect.signature(accounts_route.get_oauth_url).parameters["current_user"].annotation is accounts_route.CurrentUser
    assert inspect.signature(accounts_route.oauth_callback).parameters["current_user"].annotation is accounts_route.CurrentUser
    assert inspect.signature(accounts_route.connect_bluesky).parameters["current_user"].annotation is accounts_route.CurrentUser
    assert inspect.signature(accounts_route.connect_discord).parameters["current_user"].annotation is accounts_route.CurrentUser
    assert inspect.signature(accounts_route.save_linkedin_orgs).parameters["current_user"].annotation is accounts_route.CurrentUser
    assert inspect.signature(accounts_route.add_linkedin_page_manually).parameters["current_user"].annotation is accounts_route.CurrentUser


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

    assert account_id == "tiktok-account-1"
    assert db.social_accounts.update_calls
    _query, update, upsert = db.social_accounts.update_calls[-1]
    assert upsert is True
    set_fields = update["$set"]
    assert set_fields["publish_error_code"] is None
    assert set_fields["publish_error_category"] is None
    assert set_fields["publish_action_required"] is None
    assert set_fields["publish_restriction_type"] is None
    assert set_fields["publish_blocked_at"] is None


@pytest.mark.asyncio
async def test_exchange_linkedin_code_uses_id_token_claims_before_userinfo(monkeypatch):
    class _FakeLinkedInAuth:
        @staticmethod
        def normalize_account_type(account_type=None) -> str:
            return account_type or "profile"

        @staticmethod
        def _oauth_scopes(_account_type=None) -> str:
            return "openid profile email w_member_social"

        async def exchange_code_for_token(self, code: str) -> dict:
            assert code == "oauth-code"
            return {
                "access_token": "linkedin-access",
                "refresh_token": "linkedin-refresh",
                "expires_in": 3600,
                "id_token": "header.payload.signature",
                "scope": "openid profile email",
            }

        @staticmethod
        def _decode_jwt_payload(_token: str | None) -> dict:
            return {
                "sub": "linkedin-user-1",
                "name": "LinkedIn User",
                "email": "linkedin@example.com",
                "picture": "https://example.com/linkedin.png",
            }

        async def get_user_profile(self, _access_token: str) -> dict:
            raise AssertionError("userinfo should not be called when id_token claims are usable")

    monkeypatch.setattr(linkedin_module, "LinkedInAuth", _FakeLinkedInAuth)

    result = await accounts_route._exchange_linkedin_code("oauth-code")

    assert result is not None
    assert result["platform_user_id"] == "linkedin-user-1"
    assert result["username"] == "linkedin@example.com"
    assert result["display_name"] == "LinkedIn User"
    assert result["picture_url"] == "https://example.com/linkedin.png"
    assert result["refresh_token"] == "linkedin-refresh"
    assert result["scopes"] == ["openid", "profile", "email"]
    assert result["expires_at"] is not None
    assert result["account_type"] == "profile"
    assert result["linkedin_author_urn"] == "urn:li:person:linkedin-user-1"


@pytest.mark.asyncio
async def test_exchange_linkedin_code_falls_back_to_userinfo_when_id_token_missing_subject(monkeypatch):
    class _FakeLinkedInAuth:
        @staticmethod
        def normalize_account_type(account_type=None) -> str:
            return account_type or "profile"

        @staticmethod
        def _oauth_scopes(_account_type=None) -> str:
            return "openid profile email w_member_social"

        async def exchange_code_for_token(self, code: str) -> dict:
            assert code == "oauth-code"
            return {
                "access_token": "linkedin-access",
                "expires_in": 3600,
                "id_token": "header.payload.signature",
            }

        @staticmethod
        def _decode_jwt_payload(_token: str | None) -> dict:
            return {"email": "linkedin@example.com"}

        async def get_user_profile(self, access_token: str) -> dict:
            assert access_token == "linkedin-access"
            return {
                "sub": "linkedin-user-2",
                "name": "Fallback User",
                "email": "fallback@example.com",
            }

    monkeypatch.setattr(linkedin_module, "LinkedInAuth", _FakeLinkedInAuth)

    result = await accounts_route._exchange_linkedin_code("oauth-code")

    assert result is not None
    assert result["platform_user_id"] == "linkedin-user-2"
    assert result["username"] == "fallback@example.com"
    assert result["display_name"] == "Fallback User"
    assert result["account_type"] == "profile"
    assert result["linkedin_author_urn"] == "urn:li:person:linkedin-user-2"


@pytest.mark.asyncio
async def test_hydrate_linkedin_metadata_avoids_userinfo_when_refreshing_followers(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(accounts_route, "decrypt", lambda value: "linkedin-token")

    class _FakeLinkedInAuth:
        async def fetch_audience_analytics(self, access_token: str, account: dict, days: int | None = None) -> dict:
            assert access_token == "linkedin-token"
            assert account["platform"] == "linkedin"
            return {"followers": 87}

        async def get_user_profile(self, _access_token: str) -> dict:
            raise AssertionError("LinkedIn metadata hydration should not depend on userinfo")

    monkeypatch.setattr(linkedin_module, "LinkedInAuth", _FakeLinkedInAuth)

    db = _FakeDB([
        {
            "id": "linkedin-account-1",
            "account_id": "linkedin-account-1",
            "user_id": "user-1",
            "platform": "linkedin",
            "platform_user_id": "linkedin-user-1",
            "platform_username": "linkedin-org",
            "display_name": "LinkedIn Org",
            "picture_url": "https://example.com/logo.png",
            "access_token": "encrypted-token",
            "is_active": True,
            "connected_at": now,
            "followers_count": None,
        }
    ])

    hydrated = await accounts_route._hydrate_social_account_metadata(db, db.social_accounts.docs[0])

    assert hydrated["followers_count"] == 87
    assert hydrated["display_name"] == "LinkedIn Org"
    assert hydrated["picture_url"] == "https://example.com/logo.png"


@pytest.mark.asyncio
async def test_persist_linkedin_profile_account_sets_person_author_urn(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(accounts_route, "encrypt", lambda value: f"enc:{value}")
    db = _FakeDB([])

    account_id = await accounts_route._persist_oauth_account(
        db,
        "user-1",
        "linkedin",
        {
            "access_token": "linkedin-access",
            "refresh_token": "linkedin-refresh",
            "platform_user_id": "member-1",
            "username": "member@example.com",
            "display_name": "Member One",
            "picture_url": "https://example.com/member.png",
            "scopes": ["openid", "profile", "email", "w_member_social"],
            "expires_at": now,
            "account_type": "profile",
            "linkedin_author_urn": "urn:li:person:member-1",
        },
    )

    assert account_id.startswith("linkedin_user-1_")
    assert len(db.social_accounts.docs) == 1
    account = db.social_accounts.docs[0]
    assert account["account_type"] == "profile"
    assert account["platform_user_id"] == "member-1"
    assert account["linkedin_author_urn"] == "urn:li:person:member-1"
    assert account["is_active"] is True


@pytest.mark.asyncio
async def test_persist_linkedin_organization_flow_creates_page_account(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(accounts_route, "encrypt", lambda value: f"enc:{value}")
    db = _FakeDB([])

    class _FakeLinkedInAuth:
        async def get_manageable_organization_choices(self, access_token: str) -> list[dict]:
            assert access_token == "linkedin-access"
            return [
                {
                    "org_id": "12345",
                    "name": "Unravler Company",
                    "role": "ADMINISTRATOR",
                    "organization_urn": "urn:li:organization:12345",
                }
            ]

    monkeypatch.setattr(linkedin_module, "LinkedInAuth", _FakeLinkedInAuth)

    grant_id = await accounts_route._persist_oauth_account(
        db,
        "user-1",
        "linkedin",
        {
            "access_token": "linkedin-access",
            "refresh_token": "linkedin-refresh",
            "platform_user_id": "member-1",
            "username": "member@example.com",
            "display_name": "Member One",
            "picture_url": "https://example.com/member.png",
            "scopes": [
                "openid",
                "profile",
                "email",
                "w_member_social",
                "w_organization_social",
                "r_organization_admin",
            ],
            "expires_at": now,
            "account_type": "organization",
        },
    )

    grant = db.social_accounts.docs[0]
    assert grant["account_id"] == grant_id
    assert grant["account_type"] == "organization_grant"
    assert grant["is_active"] is False
    assert grant["parent_member_id"] == "member-1"
    assert grant["pending_orgs"][0]["org_id"] == "12345"

    page_id = await accounts_route._create_linkedin_organization_account(
        db,
        "user-1",
        grant,
        grant["pending_orgs"][0],
    )

    page = next(doc for doc in db.social_accounts.docs if doc.get("account_id") == page_id)
    assert page["account_type"] == "organization"
    assert page["platform_user_id"] == "12345"
    assert page["linkedin_org_id"] == "12345"
    assert page["linkedin_org_role"] == "ADMINISTRATOR"
    assert page["linkedin_author_urn"] == "urn:li:organization:12345"
    assert page["parent_member_id"] == "member-1"
    assert page["access_token"] == "enc:linkedin-access"


def test_linkedin_oauth_scopes_default_to_safe_connect_set(monkeypatch):
    monkeypatch.delenv("LINKEDIN_OAUTH_SCOPES", raising=False)
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "linkedin-client-id")
    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "https://api.example.com/api/oauth/linkedin/callback")

    url = accounts_route._build_oauth_url("linkedin", "state-123")
    params = parse_qs(urlparse(url).query)

    assert params["scope"] == ["openid profile email w_member_social"]


def test_linkedin_oauth_scopes_allow_env_override(monkeypatch):
    monkeypatch.setenv("LINKEDIN_OAUTH_SCOPES", "openid profile email w_member_social r_organization_admin")
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "linkedin-client-id")
    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "https://api.example.com/api/oauth/linkedin/callback")

    url = accounts_route._build_oauth_url("linkedin", "state-456")
    params = parse_qs(urlparse(url).query)

    assert params["scope"] == ["openid profile email w_member_social"]


def test_linkedin_organization_oauth_requires_company_page_scopes(monkeypatch):
    monkeypatch.setenv("LINKEDIN_OAUTH_SCOPES", "openid profile email w_member_social")
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "linkedin-client-id")
    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "https://api.example.com/api/oauth/linkedin/callback")

    with pytest.raises(accounts_route.HTTPException) as exc_info:
        linkedin_module.LinkedInAuth().get_auth_url("state-456", account_type="organization")

    assert exc_info.value.status_code == 503
    assert "company page connection is not configured" in str(exc_info.value.detail)


def test_linkedin_organization_oauth_uses_organization_scopes(monkeypatch):
    monkeypatch.setenv(
        "LINKEDIN_OAUTH_SCOPES",
        "openid profile email w_member_social w_organization_social r_organization_admin r_organization_social",
    )
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "linkedin-client-id")
    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "https://api.example.com/api/oauth/linkedin/callback")

    url = linkedin_module.LinkedInAuth().get_auth_url("state-789", account_type="organization")
    params = parse_qs(urlparse(url).query)

    assert params["scope"] == [
        "openid profile email w_member_social w_organization_social r_organization_admin r_organization_social"
    ]


def test_stateless_oauth_state_preserves_linkedin_account_type(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://app.unravler.com")
    state = accounts_route._create_stateless_oauth_state({
        "user_id": "user-1",
        "frontend_base": "https://www.unravler.com",
        "linkedin_account_type": "organization",
    })

    decoded = accounts_route._decode_stateless_oauth_state(state)

    assert decoded["user_id"] == "user-1"
    assert decoded["frontend_base"] == "https://www.unravler.com"
    assert decoded["linkedin_account_type"] == "organization"
