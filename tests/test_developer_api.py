from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.routes import api_keys as api_keys_route
from api.routes import public_api as public_api_route
from utils.developer_tokens import PERSONAL_TOKEN_TYPE, allowed_public_scopes_for_role, hash_developer_token


def _matches_value(value, expected):
  if isinstance(expected, dict):
    if "$ne" in expected and value == expected["$ne"]:
      return False
    return True
  return value == expected


def _matches_query(doc, query):
  for key, expected in (query or {}).items():
    if key == "$or":
      if not any(_matches_query(doc, branch) for branch in expected):
        return False
      continue
    if not _matches_value(doc.get(key), expected):
      return False
  return True


class _FakeCollection:
  def __init__(self, docs=None):
    self.docs = [dict(doc) for doc in (docs or [])]
    self.update_calls = []

  async def find_one(self, query, projection=None):
    for doc in self.docs:
      if _matches_query(doc, query):
        result = dict(doc)
        if projection and projection.get("_id") == 0:
          result.pop("_id", None)
        return result
    return None

  async def insert_one(self, doc):
    self.docs.append(dict(doc))
    return SimpleNamespace(inserted_id=doc.get("id"))

  async def update_one(self, query, update, upsert=False):
    self.update_calls.append((query, update, upsert))
    for doc in self.docs:
      if _matches_query(doc, query):
        for key, value in update.get("$set", {}).items():
          doc[key] = value
        return SimpleNamespace(modified_count=1)
    if upsert:
      inserted = {}
      inserted.update(update.get("$setOnInsert", {}))
      inserted.update(update.get("$set", {}))
      self.docs.append(inserted)
      return SimpleNamespace(modified_count=1)
    return SimpleNamespace(modified_count=0)


class _FakeDB:
  def __init__(self, *, users=None, workspace_members=None, workspaces=None, api_keys=None):
    self.users = _FakeCollection(users)
    self.workspace_members = _FakeCollection(workspace_members)
    self.workspaces = _FakeCollection(workspaces)
    self.api_keys = _FakeCollection(api_keys)
    self.public_api_idempotency = _FakeCollection()


class _ModelDumpResponse:
  def __init__(self, payload):
    self.payload = payload

  def model_dump(self, mode="json"):
    return dict(self.payload)


def _request(path="/api/public/me", authorization="Bearer token-123"):
  headers = []
  if authorization:
    headers.append((b"authorization", authorization.encode()))
  return Request(
    {
      "type": "http",
      "method": "GET",
      "path": path,
      "headers": headers,
      "client": ("127.0.0.1", 1234),
      "server": ("testserver", 443),
      "scheme": "https",
    }
  )


@pytest.mark.asyncio
async def test_create_personal_token_defaults_to_role_allowed_scopes():
  now = datetime.now(timezone.utc)
  db = _FakeDB(
    workspace_members=[
      {
        "workspace_id": "ws-1",
        "user_id": "user-1",
        "role": "viewer",
        "joined_at": now,
      }
    ]
  )
  current_user = {
    "user_id": "user-1",
    "default_workspace_id": "ws-1",
  }

  result = await api_keys_route.create_personal_token(
    body=api_keys_route.DeveloperTokenCreate(name="Claude token"),
    current_user=current_user,
    db=db,
  )

  assert result["token_type"] == PERSONAL_TOKEN_TYPE
  assert result["workspace_id"] == "ws-1"
  assert result["scopes"] == allowed_public_scopes_for_role("viewer")
  assert result["raw_key"].startswith("unr_")
  assert len(db.api_keys.docs) == 1


@pytest.mark.asyncio
async def test_create_personal_token_rejects_scope_beyond_workspace_role():
  now = datetime.now(timezone.utc)
  db = _FakeDB(
    workspace_members=[
      {
        "workspace_id": "ws-1",
        "user_id": "user-1",
        "role": "client",
        "joined_at": now,
      }
    ]
  )
  current_user = {
    "user_id": "user-1",
    "default_workspace_id": "ws-1",
  }

  with pytest.raises(HTTPException) as exc:
    await api_keys_route.create_personal_token(
      body=api_keys_route.DeveloperTokenCreate(name="Too strong", scopes=["posts:write"]),
      current_user=current_user,
      db=db,
    )

  assert exc.value.status_code == 403
  assert "posts:write" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_resolve_public_principal_honors_legacy_read_scope_alias():
  now = datetime.now(timezone.utc)
  raw_token = "legacy-read-token"
  db = _FakeDB(
    users=[
      {
        "user_id": "user-1",
        "email": "user@example.com",
        "default_workspace_id": "ws-1",
        "workspace_ids": ["ws-1"],
        "created_at": now,
      }
    ],
    workspace_members=[
      {
        "workspace_id": "ws-1",
        "user_id": "user-1",
        "role": "viewer",
        "joined_at": now,
      }
    ],
    api_keys=[
      {
        "id": "token-1",
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "token_type": PERSONAL_TOKEN_TYPE,
        "scopes": ["read"],
        "key_hash": hash_developer_token(raw_token),
        "revoked": False,
        "created_at": now,
      }
    ],
  )

  token_doc, current_user = await public_api_route._resolve_public_principal(
    request=_request(path="/api/public/posts", authorization=f"Bearer {raw_token}"),
    db=db,
    authorization=f"Bearer {raw_token}",
    x_api_key=None,
    required_scope="posts:read",
  )

  assert token_doc["id"] == "token-1"
  assert current_user["workspace_role"] == "viewer"
  assert current_user["default_workspace_id"] == "ws-1"


@pytest.mark.asyncio
async def test_public_get_me_returns_token_metadata(monkeypatch):
  now = datetime.now(timezone.utc)
  raw_token = "personal-token-123"
  db = _FakeDB(
    users=[
      {
        "user_id": "user-1",
        "email": "user@example.com",
        "default_workspace_id": "ws-1",
        "workspace_ids": ["ws-1"],
        "created_at": now,
      }
    ],
    workspace_members=[
      {
        "workspace_id": "ws-1",
        "user_id": "user-1",
        "role": "editor",
        "joined_at": now,
      }
    ],
    api_keys=[
      {
        "id": "token-1",
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "token_type": PERSONAL_TOKEN_TYPE,
        "name": "Claude",
        "scopes": ["posts:read", "posts:write"],
        "key_hash": hash_developer_token(raw_token),
        "revoked": False,
        "created_at": now,
      }
    ],
  )

  async def _fake_user_response(_db, user):
    return _ModelDumpResponse(
      {
        "user_id": user["user_id"],
        "email": user["email"],
        "display_name": "User One",
        "workspace_role": "editor",
        "workspace_permissions": ["post:read", "post:update", "approval:read"],
      }
    )

  monkeypatch.setattr(public_api_route.auth_route, "_build_user_response", _fake_user_response)

  payload = await public_api_route.public_get_me(
    request=_request(authorization=f"Bearer {raw_token}"),
    db=db,
    authorization=f"Bearer {raw_token}",
    x_api_key=None,
  )

  assert payload["token_id"] == "token-1"
  assert payload["token_type"] == PERSONAL_TOKEN_TYPE
  assert payload["scopes"] == ["posts:read", "posts:write"]
  assert payload["token_scopes"] == ["posts:read", "posts:write"]
