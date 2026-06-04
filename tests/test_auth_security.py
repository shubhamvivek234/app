from datetime import datetime, timezone

import pytest
from fastapi import HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from api.deps import get_current_user, require_verified_email
from api.routes import auth as auth_routes


class _FakeUsersCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return {k: v for k, v in doc.items() if k != "_id"}
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("InsertOneResult", (), {"inserted_id": doc.get("user_id")})()

    async def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                return type("UpdateResult", (), {"matched_count": 1})()
        return type("UpdateResult", (), {"matched_count": 0})()


class _FakeDB:
    def __init__(self):
        self.users = _FakeUsersCollection()


class _FakeAsyncResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        self.last_call = {"url": url, "json": json}
        return self.response


def _request_with_cookie(cookie_header="session=fake-cookie"):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/session",
            "headers": [(b"cookie", cookie_header.encode())],
        }
    )


@pytest.mark.asyncio
async def test_exchange_session_sets_cookie_and_returns_email_verified(monkeypatch):
    db = _FakeDB()
    response = Response()
    request = _request_with_cookie()
    created = {}

    monkeypatch.setattr(auth_routes, "get_firebase_app", lambda: object())

    class _FakeFirebaseAuth:
        @staticmethod
        def verify_id_token(token):
            assert token == "firebase-id-token"
            return {
                "uid": "firebase-uid-1",
                "email": "user@example.com",
                "email_verified": True,
                "name": "Alice",
                "picture": "https://cdn.example.com/avatar.png",
                "sub": "firebase-uid-1",
            }

    monkeypatch.setattr(auth_routes, "create_session_cookie", _fake_create_session_cookie(created))
    monkeypatch.setattr("firebase_admin.auth.verify_id_token", _FakeFirebaseAuth.verify_id_token)

    result = await auth_routes.exchange_session(
        request=request,
        response=response,
        body=auth_routes.SessionExchangeRequest(id_token="firebase-id-token"),
        db=db,
    )

    assert created["token"] == "firebase-id-token"
    assert result.email_verified is True
    assert result.display_name == "Alice"
    assert db.users.docs[0]["email_verified"] is True


def _fake_create_session_cookie(container):
    async def _create(response, id_token, expires_in=0):
        container["token"] = id_token
        response.set_cookie("session", "cookie-value")
        return "cookie-value"

    return _create


@pytest.mark.asyncio
async def test_request_password_reset_hides_email_not_found(monkeypatch):
    monkeypatch.setattr(auth_routes, "_FIREBASE_WEB_API_KEY", "firebase-web-key")
    monkeypatch.setattr(auth_routes, "_verify_turnstile_if_enabled", _async_noop)
    monkeypatch.setattr(
        auth_routes.httpx,
        "AsyncClient",
        lambda timeout=10.0: _FakeAsyncClient(
            _FakeAsyncResponse(
                status_code=400,
                payload={"error": {"message": "EMAIL_NOT_FOUND"}},
            )
        ),
    )

    result = await auth_routes.request_password_reset(
        request=Request({"type": "http", "method": "POST", "path": "/api/auth/password-reset/request", "headers": []}),
        body=auth_routes.PasswordResetRequest(email="missing@example.com"),
    )

    assert "reset email" in result["message"].lower()


async def _async_noop(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_get_current_user_prefers_cookie_session(monkeypatch):
    db = _FakeDB()
    db.users.docs.append(
        {
            "user_id": "usr_123",
            "firebase_uid": "firebase-uid-1",
            "email": "user@example.com",
            "email_verified": True,
            "display_name": "Cookie User",
            "avatar_url": None,
            "plan": "starter",
            "subscription_status": "free",
            "timezone": "UTC",
            "mfa_enabled": False,
            "role": "user",
            "onboarding_completed": False,
            "workspace_ids": [],
            "default_workspace_id": None,
            "created_at": datetime.now(timezone.utc),
        }
    )

    async def _fake_verify_session_cookie(request):
        return {
            "uid": "firebase-uid-1",
            "email": "user@example.com",
            "email_verified": True,
            "sub": "cookie-sub",
        }

    def _unexpected_verify_id_token(token):
        raise AssertionError("Bearer verification should not run when a valid session cookie exists")

    monkeypatch.setattr("api.deps.verify_session_cookie", _fake_verify_session_cookie)
    monkeypatch.setattr("api.deps.get_firebase_app", lambda: object())
    monkeypatch.setattr("api.deps.firebase_auth.verify_id_token", _unexpected_verify_id_token)

    user = await get_current_user(
        request=_request_with_cookie(),
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="stale-bearer"),
        db=db,
    )

    assert user["user_id"] == "usr_123"


@pytest.mark.asyncio
async def test_require_verified_email_rejects_unverified_user():
    with pytest.raises(HTTPException) as exc:
        await require_verified_email({"user_id": "usr_1", "email_verified": False})

    assert exc.value.status_code == 403
