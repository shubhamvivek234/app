import secrets
from datetime import datetime, timezone, timedelta
import pytest
from fastapi import HTTPException, Request
from starlette.datastructures import State

from api.routes import auth as auth_routes
from api.routes.auth import MagicLinkRequest, MagicLinkExchangeRequest, request_magic_link, exchange_magic_link
from utils import auth_emails as auth_emails_utils


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            # simple key-value matching
            match = True
            for k, v in query.items():
                if k == "expires_at":
                    # skip complex datetime filters for simple mock
                    continue
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                res = dict(doc)
                if projection and projection.get("_id") == 0:
                    res.pop("_id", None)
                return res
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                for key, val in update.get("$set", {}).items():
                    doc[key] = val
                return type("Result", (), {"matched_count": 1, "upserted_id": None})()

        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", {}))
            self.docs.append(new_doc)
            return type("Result", (), {"matched_count": 0, "upserted_id": "upserted"})()

        return type("Result", (), {"matched_count": 0, "upserted_id": None})()


class _FakeDB:
    def __init__(self):
        self.users = _FakeCollection()
        self.workspace_invites = _FakeCollection()
        self.workspaces = _FakeCollection()
        self.workspace_members = _FakeCollection()


class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value.encode() if isinstance(value, str) else value

    async def delete(self, key):
        self.store.pop(key, None)


class _FakeFBUser:
    def __init__(self, uid, email):
        self.uid = uid
        self.email = email


@pytest.fixture
def mock_firebase(monkeypatch):
    class FakeFirebaseAuth:
        def __init__(self):
            self.users = {}

        def get_user_by_email(self, email):
            if email not in self.users:
                import firebase_admin.auth as fb_auth
                raise fb_auth.UserNotFoundError("user not found")
            return self.users[email]

        def create_user(self, email, email_verified=True):
            uid = f"fb_{secrets.token_hex(6)}"
            user = _FakeFBUser(uid, email)
            self.users[email] = user
            return user

        def create_custom_token(self, uid):
            return f"custom_token_for_{uid}".encode()

    fake_auth = FakeFirebaseAuth()
    monkeypatch.setattr("firebase_admin.auth.get_user_by_email", fake_auth.get_user_by_email)
    monkeypatch.setattr("firebase_admin.auth.create_user", fake_auth.create_user)
    monkeypatch.setattr("firebase_admin.auth.create_custom_token", fake_auth.create_custom_token)
    monkeypatch.setattr("api.deps.get_firebase_app", lambda: object())
    monkeypatch.setattr("api.routes.auth.get_firebase_app", lambda: object())
    return fake_auth


@pytest.fixture(autouse=True)
def mock_notifications(monkeypatch):
    monkeypatch.setattr("celery_workers.tasks.notifications.send_notification_email_task.apply_async", lambda *args, **kwargs: None)
    monkeypatch.setattr("celery_workers.tasks.notifications.send_notification_email_task.delay", lambda *args, **kwargs: None)


@pytest.fixture
def mock_emails(monkeypatch):
    sent_emails = []

    async def fake_send_magic_link_email(email, token, display_name=None):
        sent_emails.append({"email": email, "token": token, "display_name": display_name})

    monkeypatch.setattr("api.routes.auth.send_magic_link_email", fake_send_magic_link_email)
    monkeypatch.setattr("api.routes.auth.get_auth_email_config_status", lambda: {"configured": True, "frontend_url": "http://localhost:3000"})
    return sent_emails


def _request() -> Request:
    req = Request({"type": "http", "method": "POST", "path": "/auth/magic-link/request", "headers": []})
    req.state.client = type("Client", (), {"host": "127.0.0.1"})
    return req


@pytest.mark.asyncio
async def test_request_magic_link_success(mock_emails):
    db = _FakeDB()
    db.users.docs.append({
        "user_id": "usr_1",
        "email": "test@example.com",
        "display_name": "Test User",
    })
    redis = _FakeRedis()

    body = MagicLinkRequest(email="test@example.com")
    resp = await request_magic_link(
        request=_request(),
        body=body,
        db=db,
        cache_redis=redis,
    )

    assert "magic login link will be sent" in resp["message"]
    assert len(mock_emails) == 1
    assert mock_emails[0]["email"] == "test@example.com"
    
    # Check that Redis token matches email
    token = mock_emails[0]["token"]
    stored_email = await redis.get(f"magic_link:{token}")
    assert stored_email.decode() == "test@example.com"


@pytest.mark.asyncio
async def test_exchange_magic_link_success(mock_firebase):
    db = _FakeDB()
    redis = _FakeRedis()
    token = "some-magic-token"
    await redis.setex(f"magic_link:{token}", 3600, "test@example.com")

    # firebase initially doesn't have the user -> will auto-provision
    body = MagicLinkExchangeRequest(token=token)
    resp = await exchange_magic_link(
        request=_request(),
        body=body,
        db=db,
        cache_redis=redis,
    )

    assert resp["email"] == "test@example.com"
    assert resp["custom_token"].startswith("custom_token_for_fb_")
    
    # MongoDB user should be auto-created
    mongo_user = await db.users.find_one({"email": "test@example.com"})
    assert mongo_user is not None
    assert mongo_user["email_verified"] is True

    # Invalidation check (single-use token)
    redis_val = await redis.get(f"magic_link:{token}")
    assert redis_val is None


@pytest.mark.asyncio
async def test_exchange_magic_link_invalid_token():
    db = _FakeDB()
    redis = _FakeRedis()
    body = MagicLinkExchangeRequest(token="invalid-token")

    with pytest.raises(HTTPException) as exc:
        await exchange_magic_link(
            request=_request(),
            body=body,
            db=db,
            cache_redis=redis,
        )

    assert exc.value.status_code == 400
    assert "expired or is invalid" in exc.value.detail


@pytest.mark.asyncio
async def test_exchange_magic_link_with_invite_token(mock_firebase):
    db = _FakeDB()
    redis = _FakeRedis()
    invite_token = "invite-123"
    
    # Save invite in DB
    db.workspace_invites.docs.append({
        "invite_id": "inv_1",
        "token": invite_token,
        "email": "client@example.com",
        "role": "client",
        "status": "pending",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    })

    body = MagicLinkExchangeRequest(token=invite_token)
    resp = await exchange_magic_link(
        request=_request(),
        body=body,
        db=db,
        cache_redis=redis,
    )

    assert resp["email"] == "client@example.com"
    assert resp["is_invite"] is True
    
    # MongoDB client user should be auto-created
    mongo_user = await db.users.find_one({"email": "client@example.com"})
    assert mongo_user is not None
    assert mongo_user["email_verified"] is True
