"""Unit tests for developer OAuth2 Applications registration endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routes.oauth_apps import router as oauth_apps_router
from api.deps import get_current_user, get_db


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.oauth_applications = MagicMock()
    db.workspace_members = MagicMock()
    db.workspaces = MagicMock()
    db.users = MagicMock()
    db.users.update_one = AsyncMock()
    return db


@pytest.fixture
def test_app(mock_db):
    app = FastAPI()
    app.include_router(oauth_apps_router, prefix="/api")

    async def override_user():
        return {
            "user_id": "test_user_1",
            "default_workspace_id": "ws_123",
            "workspace_ids": ["ws_123"],
            "email_verified": True,
        }

    async def override_db():
        return mock_db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return app


@pytest.mark.asyncio
async def test_create_and_list_oauth_app(test_app, mock_db):
    mock_db.workspace_members.find_one = AsyncMock(return_value={"role": "admin"})
    mock_db.oauth_applications.count_documents = AsyncMock(return_value=0)
    mock_db.oauth_applications.insert_one = AsyncMock()

    created_oid = ObjectId()
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[
        {
            "_id": created_oid,
            "name": "Integration App",
            "client_id": "unr_app_abc123",
            "redirect_uris": ["https://example.com/oauth/callback"],
            "description": "Test App",
            "created_at": "2026-09-20T00:00:00Z",
            "is_active": True,
        }
    ])
    mock_db.oauth_applications.find = MagicMock(return_value=mock_cursor)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        create_resp = await ac.post("/api/developer/apps", json={
            "name": "Integration App",
            "redirect_uris": ["https://example.com/oauth/callback"],
            "description": "Test App",
        })
        assert create_resp.status_code == 201
        data = create_resp.json()
        assert data["name"] == "Integration App"
        assert data["client_id"].startswith("unr_app_")
        assert data["client_secret"].startswith("unr_sec_")

        list_resp = await ac.get("/api/developer/apps")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert len(list_data) == 1
        assert list_data[0]["client_secret"] is None  # secret should not be in list


@pytest.mark.asyncio
async def test_rotate_secret_and_delete_oauth_app(test_app, mock_db):
    mock_db.workspace_members.find_one = AsyncMock(return_value={"role": "owner"})
    app_id = str(ObjectId())

    mock_db.oauth_applications.find_one = AsyncMock(return_value={
        "_id": ObjectId(app_id),
        "workspace_id": "ws_123",
        "name": "Rotating App",
        "client_id": "unr_app_rot123",
        "redirect_uris": ["https://example.com/cb"],
        "created_at": "2026-09-20T00:00:00Z",
        "is_active": True,
    })
    mock_db.oauth_applications.update_one = AsyncMock(return_value=MagicMock(matched_count=1))

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        rot_resp = await ac.post(f"/api/developer/apps/{app_id}/rotate-secret")
        assert rot_resp.status_code == 200
        data = rot_resp.json()
        assert data["client_secret"].startswith("unr_sec_")

        del_resp = await ac.delete(f"/api/developer/apps/{app_id}")
        assert del_resp.status_code == 204
