from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import team as team_route


def _matches_value(value, expected):
    if isinstance(expected, dict):
        if "$exists" in expected and (value is not None) != bool(expected["$exists"]):
            return False
        if "$ne" in expected and value == expected["$ne"]:
            return False
        if "$gt" in expected and not (value is not None and value > expected["$gt"]):
            return False
        if "$lte" in expected and not (value is not None and value <= expected["$lte"]):
            return False
        return True
    return value == expected


def _matches_query(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches_query(doc, branch) for branch in expected):
                return False
            continue
        if not _matches_value(doc.get(key), expected):
            return False
    return True


class FakeCursor:
    def __init__(self, docs):
        self._docs = [dict(doc) for doc in docs]

    def sort(self, spec, direction=None):
        docs = list(self._docs)
        if isinstance(spec, list):
            for key, sort_direction in reversed(spec):
                docs.sort(key=lambda doc: doc.get(key) or datetime.min.replace(tzinfo=timezone.utc), reverse=sort_direction < 0)
        else:
            docs.sort(key=lambda doc: doc.get(spec) or datetime.min.replace(tzinfo=timezone.utc), reverse=(direction or -1) < 0)
        self._docs = docs
        return self

    async def to_list(self, _length=None):
        return list(self._docs)


class FakeCollection:
    def __init__(self, docs=None, key_fields=None):
        self.docs = [dict(doc) for doc in (docs or [])]
        self.key_fields = key_fields or []

    def find(self, query=None, _projection=None):
        filtered = [dict(doc) for doc in self.docs if _matches_query(doc, query or {})]
        return FakeCursor(filtered)

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
        return SimpleNamespace(inserted_id=doc.get("invite_id") or doc.get("user_id"))

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _matches_query(doc, query):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                for key, value in update.get("$addToSet", {}).items():
                    current = list(doc.get(key) or [])
                    if value not in current:
                        current.append(value)
                    doc[key] = current
                return SimpleNamespace(modified_count=1, matched_count=1, deleted_count=0)

        if upsert:
            new_doc = dict(query)
            for key, value in update.get("$setOnInsert", {}).items():
                new_doc[key] = value
            self.docs.append(new_doc)
            return SimpleNamespace(modified_count=0, matched_count=0, deleted_count=0, upserted_id=new_doc.get("user_id"))

        return SimpleNamespace(modified_count=0, matched_count=0, deleted_count=0)

    async def delete_one(self, query):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not _matches_query(doc, query)]
        return SimpleNamespace(deleted_count=before - len(self.docs))

    async def find_one_and_update(self, query, update, return_document=True, projection=None):
        for doc in self.docs:
            if _matches_query(doc, query):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                result = dict(doc)
                if projection and projection.get("_id") == 0:
                    result.pop("_id", None)
                return result
        return None


class FakeDB:
    def __init__(self, *, workspace_members=None, workspace_invites=None, users=None, workspaces=None):
        self.workspace_members = FakeCollection(workspace_members)
        self.workspace_invites = FakeCollection(workspace_invites)
        self.users = FakeCollection(users)
        self.workspaces = FakeCollection(workspaces)


@pytest.mark.asyncio
async def test_list_members_returns_workspace_payload_with_pending_invites(monkeypatch):
    now = datetime.now(timezone.utc)
    db = FakeDB(
        workspace_members=[
            {"workspace_id": "ws-1", "user_id": "owner-1", "role": "owner", "joined_at": now - timedelta(days=5)},
            {"workspace_id": "ws-1", "user_id": "editor-1", "role": "editor", "joined_at": now - timedelta(days=2)},
        ],
        workspace_invites=[
            {
                "invite_id": "invite-1",
                "workspace_id": "ws-1",
                "invited_by": "owner-1",
                "email": "client@example.com",
                "role": "client",
                "token": "abc123",
                "status": "pending",
                "created_at": now - timedelta(hours=1),
                "expires_at": now + timedelta(days=6),
            }
        ],
        users=[
            {"user_id": "owner-1", "display_name": "Owner One", "email": "owner@example.com"},
            {"user_id": "editor-1", "display_name": "Editor One", "email": "editor@example.com"},
        ],
        workspaces=[{"workspace_id": "ws-1", "name": "Marketing"}],
    )

    current_user = {"user_id": "owner-1", "default_workspace_id": "ws-1"}

    result = await team_route.list_members(current_user, db)

    assert result["workspace_id"] == "ws-1"
    assert result["workspace_name"] == "Marketing"
    assert result["current_user_role"] == "owner"
    assert result["permissions"]["can_invite"] is True
    assert [member["role"] for member in result["members"]] == ["owner", "editor"]
    assert result["pending_invites"][0]["invite_url"].endswith("/accept-invite/abc123")


@pytest.mark.asyncio
async def test_invite_member_returns_shareable_invite_and_blocks_duplicates():
    now = datetime.now(timezone.utc)
    db = FakeDB(
        workspace_members=[{"workspace_id": "ws-1", "user_id": "owner-1", "role": "owner", "joined_at": now}],
        users=[{"user_id": "owner-1", "email": "owner@example.com", "display_name": "Owner One"}],
        workspaces=[{"workspace_id": "ws-1", "name": "Marketing"}],
    )
    current_user = {
        "user_id": "owner-1",
        "default_workspace_id": "ws-1",
        "email_verified": True,
    }

    created = await team_route.invite_member(
        team_route.InviteRequest(email="client@example.com", role="client"),
        current_user,
        db,
    )

    assert created["invited"] is True
    assert created["invite"]["email"] == "client@example.com"
    assert created["invite"]["invite_url"].startswith("https://")

    with pytest.raises(HTTPException) as exc:
        await team_route.invite_member(
            team_route.InviteRequest(email="client@example.com", role="client"),
            current_user,
            db,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_accept_invite_requires_matching_verified_email_and_switches_workspace():
    now = datetime.now(timezone.utc)
    db = FakeDB(
        workspace_members=[{"workspace_id": "ws-home", "user_id": "user-1", "role": "owner", "joined_at": now - timedelta(days=10)}],
        workspace_invites=[
            {
                "invite_id": "invite-1",
                "workspace_id": "ws-team",
                "invited_by": "owner-1",
                "email": "invitee@example.com",
                "role": "editor",
                "token": "join123",
                "status": "pending",
                "created_at": now - timedelta(hours=1),
                "updated_at": now - timedelta(hours=1),
                "expires_at": now + timedelta(days=7),
            }
        ],
        users=[
            {"user_id": "owner-1", "email": "owner@example.com", "display_name": "Owner One", "workspace_ids": ["ws-team"], "default_workspace_id": "ws-team"},
            {"user_id": "user-1", "email": "invitee@example.com", "display_name": "Invitee", "workspace_ids": ["ws-home"], "default_workspace_id": "ws-home"},
        ],
        workspaces=[{"workspace_id": "ws-team", "name": "Team Workspace"}],
    )

    with pytest.raises(HTTPException) as mismatch_exc:
        await team_route.accept_invite(
            "join123",
            {"user_id": "user-2", "email": "wrong@example.com", "email_verified": True},
            db,
        )
    assert mismatch_exc.value.status_code == 403

    with pytest.raises(HTTPException) as verify_exc:
        await team_route.accept_invite(
            "join123",
            {"user_id": "user-1", "email": "invitee@example.com", "email_verified": False},
            db,
        )
    assert verify_exc.value.status_code == 403

    accepted = await team_route.accept_invite(
        "join123",
        {"user_id": "user-1", "email": "invitee@example.com", "email_verified": True},
        db,
    )

    assert accepted["accepted"] is True
    assert accepted["workspace_id"] == "ws-team"
    user_doc = await db.users.find_one({"user_id": "user-1"})
    assert user_doc["default_workspace_id"] == "ws-team"
    assert "ws-team" in user_doc["workspace_ids"]
    assert await db.workspace_members.find_one({"workspace_id": "ws-team", "user_id": "user-1"}) is not None
    invite_doc = await db.workspace_invites.find_one({"invite_id": "invite-1"})
    assert invite_doc["status"] == "accepted"


@pytest.mark.asyncio
async def test_revoke_invite_marks_pending_invite_revoked():
    now = datetime.now(timezone.utc)
    db = FakeDB(
        workspace_invites=[
            {
                "invite_id": "invite-1",
                "workspace_id": "ws-1",
                "invited_by": "owner-1",
                "email": "client@example.com",
                "role": "client",
                "token": "join123",
                "status": "pending",
                "created_at": now,
                "expires_at": now + timedelta(days=7),
            }
        ]
    )

    await team_route.revoke_invite("invite-1", {"user_id": "owner-1", "default_workspace_id": "ws-1"}, db)

    invite_doc = await db.workspace_invites.find_one({"invite_id": "invite-1"})
    assert invite_doc["status"] == "revoked"
