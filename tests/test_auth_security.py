from datetime import datetime, timezone

import pytest
from fastapi import HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from api import health as health_routes
from api.deps import get_current_user, require_verified_email
from api.routes import auth as auth_routes
from utils import auth_emails as auth_emails_utils
from utils.auth_emails import (
    AuthEmailConfigError,
    AuthEmailDeliveryError,
    AuthEmailUnknownRecipientError,
)


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
    def __init__(self, response, call_store=None):
        self.response = response
        self.call_store = call_store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        self.last_call = {"url": url, "json": json}
        if self.call_store is not None:
            self.call_store["last_call"] = self.last_call
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
async def test_request_password_reset_hides_unknown_or_invalid_email(monkeypatch):
    monkeypatch.setattr(auth_routes, "_verify_turnstile_if_enabled", _async_noop)
    monkeypatch.setattr(
        auth_routes,
        "get_auth_email_config_status",
        lambda: {
            "configured": True,
            "missing": [],
            "sender_email": "contact@unravler.com",
            "custom_link_domain_configured": True,
        },
    )

    async def _raise_unknown(email):
        raise AuthEmailUnknownRecipientError(email)

    monkeypatch.setattr(auth_routes, "send_password_reset_email", _raise_unknown)

    result = await auth_routes.request_password_reset(
        request=Request({"type": "http", "method": "POST", "path": "/api/auth/password-reset/request", "headers": []}),
        body=auth_routes.PasswordResetRequest(email="missing@example.com"),
    )

    assert "reset email" in result["message"].lower()


@pytest.mark.asyncio
async def test_request_password_reset_returns_503_when_auth_email_config_missing(monkeypatch):
    monkeypatch.setattr(auth_routes, "_verify_turnstile_if_enabled", _async_noop)
    monkeypatch.setattr(
        auth_routes,
        "get_auth_email_config_status",
        lambda: {
            "configured": False,
            "missing": ["RESEND_API_KEY", "SENDER_EMAIL"],
        },
    )

    with pytest.raises(HTTPException) as exc:
        await auth_routes.request_password_reset(
            request=Request({"type": "http", "method": "POST", "path": "/api/auth/password-reset/request", "headers": []}),
            body=auth_routes.PasswordResetRequest(email="missing@example.com"),
        )

    assert exc.value.status_code == 503
    assert "temporarily unavailable" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_request_password_reset_uses_branded_sender_and_calls_helper(monkeypatch):
    monkeypatch.setattr(auth_routes, "_verify_turnstile_if_enabled", _async_noop)
    monkeypatch.setattr(
        auth_routes,
        "get_auth_email_config_status",
        lambda: {
            "configured": True,
            "missing": [],
            "sender_email": "contact@unravler.com",
            "custom_link_domain_configured": True,
        },
    )
    call_store = {}

    async def _send(email):
        call_store["email"] = email

    monkeypatch.setattr(auth_routes, "send_password_reset_email", _send)

    result = await auth_routes.request_password_reset(
        request=Request({"type": "http", "method": "POST", "path": "/api/auth/password-reset/request", "headers": []}),
        body=auth_routes.PasswordResetRequest(email="user@example.com"),
    )

    assert "reset email" in result["message"].lower()
    assert call_store["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_request_password_reset_hides_unexpected_provider_failures(monkeypatch):
    monkeypatch.setattr(auth_routes, "_verify_turnstile_if_enabled", _async_noop)
    monkeypatch.setattr(
        auth_routes,
        "get_auth_email_config_status",
        lambda: {
            "configured": True,
            "missing": [],
            "sender_email": "contact@unravler.com",
            "custom_link_domain_configured": True,
        },
    )

    async def _raise_delivery(email):
        raise AuthEmailDeliveryError("provider unavailable")

    monkeypatch.setattr(auth_routes, "send_password_reset_email", _raise_delivery)

    result = await auth_routes.request_password_reset(
        request=Request({"type": "http", "method": "POST", "path": "/api/auth/password-reset/request", "headers": []}),
        body=auth_routes.PasswordResetRequest(email="user@example.com"),
    )

    assert "reset email" in result["message"].lower()


@pytest.mark.asyncio
async def test_send_password_reset_email_falls_back_to_firebase_managed_email(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "resend_test")
    monkeypatch.setenv("SENDER_EMAIL", "contact@unravler.com")
    monkeypatch.setenv("FRONTEND_URL", "https://www.unravler.com")
    monkeypatch.setenv("FIREBASE_WEB_API_KEY", "firebase-web-key")

    monkeypatch.setattr(auth_emails_utils, "get_firebase_app", lambda: object())

    def _raise_invalid_signature(*args, **kwargs):
        raise RuntimeError("invalid_grant: Invalid JWT Signature.")

    monkeypatch.setattr(auth_emails_utils.firebase_auth, "generate_password_reset_link", _raise_invalid_signature)
    call_store = {}

    async def _fallback(email):
        call_store["email"] = email

    monkeypatch.setattr(auth_emails_utils, "_send_password_reset_via_firebase", _fallback)

    await auth_emails_utils.send_password_reset_email("user@example.com")

    assert call_store["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_send_password_reset_email_raises_when_branded_and_fallback_both_fail(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "resend_test")
    monkeypatch.setenv("SENDER_EMAIL", "contact@unravler.com")
    monkeypatch.setenv("FRONTEND_URL", "https://www.unravler.com")
    monkeypatch.setenv("FIREBASE_WEB_API_KEY", "firebase-web-key")

    monkeypatch.setattr(auth_emails_utils, "get_firebase_app", lambda: object())

    def _raise_invalid_signature(*args, **kwargs):
        raise RuntimeError("invalid_grant: Invalid JWT Signature.")

    monkeypatch.setattr(auth_emails_utils.firebase_auth, "generate_password_reset_link", _raise_invalid_signature)

    async def _fallback(email):
        raise AuthEmailDeliveryError("firebase fallback failed")

    monkeypatch.setattr(auth_emails_utils, "_send_password_reset_via_firebase", _fallback)

    with pytest.raises(AuthEmailDeliveryError):
        await auth_emails_utils.send_password_reset_email("user@example.com")


@pytest.mark.asyncio
async def test_request_verification_email_sends_branded_email(monkeypatch):
    monkeypatch.setattr(
        auth_routes,
        "get_auth_email_config_status",
        lambda: {
            "configured": True,
            "missing": [],
            "sender_email": "contact@unravler.com",
            "custom_link_domain_configured": True,
        },
    )
    call_store = {}

    async def _send(email, *, display_name=None, return_to=None):
        call_store["email"] = email
        call_store["display_name"] = display_name
        call_store["return_to"] = return_to

    monkeypatch.setattr(auth_routes, "send_verification_email", _send)

    result = await auth_routes.request_verification_email(
        request=Request({"type": "http", "method": "POST", "path": "/api/auth/verify-email/request", "headers": []}),
        current_user={
            "user_id": "usr_123",
            "email": "user@example.com",
            "display_name": "Alice",
            "email_verified": False,
        },
        body=auth_routes.VerifyEmailRequest(return_to="/accept-invite/token"),
    )

    assert "verification email sent" in result["message"].lower()
    assert call_store == {
        "email": "user@example.com",
        "display_name": "Alice",
        "return_to": "/accept-invite/token",
    }


@pytest.mark.asyncio
async def test_request_verification_email_returns_503_when_delivery_unavailable(monkeypatch):
    monkeypatch.setattr(
        auth_routes,
        "get_auth_email_config_status",
        lambda: {
            "configured": True,
            "missing": [],
            "sender_email": "contact@unravler.com",
            "custom_link_domain_configured": True,
        },
    )

    async def _raise_delivery(email, *, display_name=None, return_to=None):
        raise AuthEmailDeliveryError("resend down")

    monkeypatch.setattr(auth_routes, "send_verification_email", _raise_delivery)

    with pytest.raises(HTTPException) as exc:
        await auth_routes.request_verification_email(
            request=Request({"type": "http", "method": "POST", "path": "/api/auth/verify-email/request", "headers": []}),
            current_user={
                "user_id": "usr_123",
                "email": "user@example.com",
                "display_name": "Alice",
                "email_verified": False,
            },
            body=auth_routes.VerifyEmailRequest(),
        )

    assert exc.value.status_code == 503
    assert "temporarily unavailable" in exc.value.detail.lower()


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


class _FakeAdmin:
    async def command(self, name):
        assert name == "ping"
        return {"ok": 1}


class _FakeMongoClient:
    def __init__(self):
        self.admin = _FakeAdmin()


class _FakeRedis:
    async def ping(self):
        return True


@pytest.mark.asyncio
async def test_ready_reports_password_reset_config_as_degraded_without_failing(monkeypatch):
    async def _fake_get_mongo_client():
        return _FakeMongoClient()

    async def _fake_validate_storage():
        return {"backend": "r2"}

    monkeypatch.setattr(health_routes, "get_mongo_client", _fake_get_mongo_client)
    monkeypatch.setattr(health_routes, "get_queue_redis", lambda: _FakeRedis())
    monkeypatch.setattr(health_routes, "get_cache_redis", lambda: _FakeRedis())
    monkeypatch.setattr(health_routes, "get_firebase_app", lambda: object())
    monkeypatch.setattr(health_routes, "validate_storage_backend_async", _fake_validate_storage)
    monkeypatch.setattr(
        health_routes,
        "get_password_reset_config_status",
        lambda: {
            "configured": False,
            "missing": ["RESEND_API_KEY", "SENDER_EMAIL"],
            "custom_link_domain_configured": False,
            "custom_sender_configured": False,
        },
    )

    response = await health_routes.ready()

    assert response.status_code == 200
    assert response.body
    assert b'"status":"degraded"' in response.body
    assert b'"auth_password_reset":"degraded:missing_RESEND_API_KEY_SENDER_EMAIL"' in response.body
