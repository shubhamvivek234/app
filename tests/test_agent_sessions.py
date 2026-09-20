"""Unit tests for AI Agent Hub sessions, chat conversations, and action cards."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routes.agent import router as agent_router
from api.deps import get_current_user, get_db, require_verified_email


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.agent_sessions = MagicMock()
    db.agent_messages = MagicMock()
    db.social_accounts = MagicMock()
    return db


@pytest.fixture
def test_app(mock_db):
    app = FastAPI()
    app.include_router(agent_router, prefix="/api")

    async def override_user():
        return {
            "user_id": "test_user_operator",
            "default_workspace_id": "ws_agent_1",
            "workspace_ids": ["ws_agent_1"],
            "email_verified": True,
        }

    async def override_db():
        return mock_db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[require_verified_email] = override_user
    app.dependency_overrides[get_db] = override_db
    return app


@pytest.mark.asyncio
async def test_create_and_list_agent_sessions(test_app, mock_db):
    mock_db.agent_sessions.insert_one = AsyncMock()
    mock_db.agent_messages.insert_one = AsyncMock()

    # Test creating a session
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        res = await client.post(
            "/api/agent/sessions",
            json={"title": "Q4 Growth Sprint", "channel_ids": ["acc_x1", "acc_li1"]},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["title"] == "Q4 Growth Sprint"
        assert data["channel_ids"] == ["acc_x1", "acc_li1"]
        assert "id" in data
        assert data["message_count"] == 1
        assert mock_db.agent_sessions.insert_one.called
        assert mock_db.agent_messages.insert_one.called

    # Test listing sessions
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[
        {
            "id": data["id"],
            "workspace_id": "ws_agent_1",
            "user_id": "test_user_operator",
            "title": "Q4 Growth Sprint",
            "channel_ids": ["acc_x1", "acc_li1"],
            "created_at": "2026-09-20T00:00:00Z",
            "updated_at": "2026-09-20T00:00:00Z",
        }
    ])
    mock_db.agent_sessions.find = MagicMock(return_value=mock_cursor)
    mock_db.agent_messages.count_documents = AsyncMock(return_value=2)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        list_res = await client.get("/api/agent/sessions")
        assert list_res.status_code == 200
        items = list_res.json()
        assert len(items) == 1
        assert items[0]["title"] == "Q4 Growth Sprint"
        assert items[0]["message_count"] == 2


@pytest.mark.asyncio
async def test_get_session_details_and_history(test_app, mock_db):
    session_id = "sess_xyz_123"
    mock_db.agent_sessions.find_one = AsyncMock(return_value={
        "id": session_id,
        "workspace_id": "ws_agent_1",
        "title": "Launch Thread",
        "channel_ids": [],
        "created_at": "2026-09-20T00:00:00Z",
        "updated_at": "2026-09-20T00:00:00Z",
    })
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[
        {
            "id": "msg_1",
            "session_id": session_id,
            "sender": "assistant",
            "text": "Hello, how can I help?",
            "cards": [],
            "created_at": "2026-09-20T00:00:00Z",
        }
    ])
    mock_db.agent_messages.find = MagicMock(return_value=mock_cursor)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        res = await client.get(f"/api/agent/sessions/{session_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["session"]["id"] == session_id
        assert len(body["messages"]) == 1
        assert body["messages"][0]["text"] == "Hello, how can I help?"


@pytest.mark.asyncio
async def test_chat_interaction_draft_intent(test_app, mock_db):
    session_id = "sess_xyz_123"
    mock_db.agent_sessions.find_one = AsyncMock(return_value={
        "id": session_id,
        "workspace_id": "ws_agent_1",
        "title": "New Strategy Thread",
        "channel_ids": ["acc_1"],
    })
    mock_db.agent_messages.insert_one = AsyncMock()
    mock_db.agent_messages.count_documents = AsyncMock(return_value=2)
    mock_db.agent_sessions.update_one = AsyncMock()

    mock_acc_cursor = MagicMock()
    mock_acc_cursor.to_list = AsyncMock(return_value=[
        {"id": "acc_1", "platform": "twitter", "platform_username": "unravlerhq"}
    ])
    mock_db.social_accounts.find = MagicMock(return_value=mock_acc_cursor)

    with patch("api.routes.agent.free_llm.generate_text", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = (
            "Excited to announce our new feature release today! #buildinpublic",
            "groq",
            "llama-3",
        )

        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.post(
                f"/api/agent/sessions/{session_id}/chat",
                json={"message": "Draft an announcement post about our feature launch", "channel_ids": ["acc_1"]},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["session_id"] == session_id
            assert "Excited to announce" in data["reply"]
            assert len(data["cards"]) >= 1

            draft_card = next(c for c in data["cards"] if c["card_type"] == "draft_post")
            assert draft_card is not None
            assert draft_card["payload"]["platforms"] == ["twitter"]
            assert draft_card["payload"]["content"] == data["reply"]
            assert any(a["action"] == "open_composer" for a in draft_card["actions"])


@pytest.mark.asyncio
async def test_chat_interaction_youtube_clipping_intent(test_app, mock_db):
    session_id = "sess_xyz_123"
    mock_db.agent_sessions.find_one = AsyncMock(return_value={
        "id": session_id,
        "workspace_id": "ws_agent_1",
        "title": "Video Strategy",
        "channel_ids": [],
    })
    mock_db.agent_messages.insert_one = AsyncMock()
    mock_db.agent_messages.count_documents = AsyncMock(return_value=4)
    mock_db.agent_sessions.update_one = AsyncMock()

    mock_acc_cursor = MagicMock()
    mock_acc_cursor.to_list = AsyncMock(return_value=[])
    mock_db.social_accounts.find = MagicMock(return_value=mock_acc_cursor)

    with patch("api.routes.agent.free_llm.generate_text", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = (
            "I detected your YouTube video and can extract top viral clips for TikTok and Reels!",
            "groq",
            "llama-3",
        )

        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            res = await client.post(
                f"/api/agent/sessions/{session_id}/chat",
                json={"message": "Clip this video for me: https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )
            assert res.status_code == 200
            data = res.json()
            clipping_cards = [c for c in data["cards"] if c["card_type"] == "clipping_job"]
            assert len(clipping_cards) == 1
            card = clipping_cards[0]
            assert "dQw4w9WgXcQ" in card["title"]
            assert card["actions"][0]["action"] == "clip_video"


@pytest.mark.asyncio
async def test_delete_agent_session(test_app, mock_db):
    session_id = "sess_to_delete"
    mock_db.agent_sessions.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    mock_db.agent_messages.delete_many = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        res = await client.delete(f"/api/agent/sessions/{session_id}")
        assert res.status_code == 200
        assert res.json()["success"] is True
        assert mock_db.agent_sessions.delete_one.called
        assert mock_db.agent_messages.delete_many.called
