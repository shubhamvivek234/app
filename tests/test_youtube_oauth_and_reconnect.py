from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from api.routes.accounts import _build_oauth_url
from utils.ghost_cascade import handle_account_reconnect_required


def test_youtube_oauth_url_requests_publish_edit_scopes(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id")

    auth_url = _build_oauth_url("youtube", "state-123", "https://www.unravler.com")
    params = parse_qs(urlparse(auth_url).query)

    assert params["client_id"] == ["google-client-id"]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["include_granted_scopes"] == ["true"]
    assert params["redirect_uri"] == ["https://www.unravler.com/oauth/callback"]
    assert "https://www.googleapis.com/auth/youtube.force-ssl" in params["scope"][0]


class _FakeSocialAccounts:
    def __init__(self):
        self.updated = []

    async def find_one_and_update(self, query, update, return_document=True):
        self.updated.append((query, update))
        return {
            "user_id": "usr_123",
            "platform": "youtube",
            "display_name": "Prodcaster",
        }


class _FakePosts:
    def __init__(self):
        self.queries = []

    async def update_many(self, query, update):
        self.queries.append((query, update))
        return SimpleNamespace(modified_count=1)


class _FakeNotifications:
    def __init__(self):
        self.inserted = []

    async def insert_one(self, payload):
        self.inserted.append(payload)


class _FakeDB:
    def __init__(self):
        self.social_accounts = _FakeSocialAccounts()
        self.posts = _FakePosts()
        self.notifications = _FakeNotifications()


@pytest.mark.asyncio
async def test_handle_account_reconnect_required_pauses_and_notifies():
    db = _FakeDB()

    result = await handle_account_reconnect_required(
        db,
        "youtube_account_1",
        "Missing required YouTube publish permissions.",
        error_code="insufficient_scopes",
    )

    assert result == {"paused_count": 2, "account_id": "youtube_account_1"}
    assert len(db.posts.queries) == 2
    assert db.notifications.inserted[0]["type"] == "account.reconnect_required"
    assert "needs to be reconnected" in db.notifications.inserted[0]["message"]
    assert "Prodcaster" in db.notifications.inserted[0]["message"]
