"""Review RBAC, tenant isolation, stale content and exact audio previews."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_current_user, get_db
from outreach.api.content_approvals import router
from outreach.core.content_approval import ContentApproval, sequence_binding
from tests.test_outreach_execution_outbox import execution_db


def client(db, role="admin", ws="w"):
    db.workspace_members.docs.append({"workspace_id": ws, "user_id": "human", "role": role})
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "human", "default_workspace_id": ws, "workspace_ids": [ws]}
    return TestClient(app)


@pytest.mark.parametrize("role", ["viewer", "editor"])
def test_content_review_requires_management_permission(role):
    api = client(execution_db(), role)
    assert api.get("/content-approvals").status_code == 403
    assert api.post("/content-approvals/prepare/c").status_code == 403
    assert api.post("/content-approvals/review/decision", json={"decision": "approve", "revision": 1, "reviewed": True}).status_code == 403


@pytest.mark.asyncio
async def test_offline_prepare_exact_content_and_stale_review(monkeypatch):
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "false")
    db = execution_db()
    api = client(db)
    assert api.post("/content-approvals/prepare/c").json()["prepared"] == 1
    item = api.get("/content-approvals").json()["items"][0]
    assert item["content"] == {"body": "Hello"}
    assert item["current"]
    path = f"/content-approvals/{item['id']}/decision"
    assert api.post(path, json={"decision": "approve", "revision": 1}).status_code == 409
    assert api.post(path, json={"decision": "approve", "revision": 1, "reviewed": True}).status_code == 200
    assert not db.outreach_sender_execution.docs
    db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"]["config"]["body"] = "New content"
    assert api.post(path, json={"decision": "approve", "revision": 2, "reviewed": True}).status_code == 409
    assert api.get("/content-approvals?view=history").json()["items"][0]["current"] is False


@pytest.mark.asyncio
async def test_review_cannot_read_other_workspace_audio_or_decide():
    db = execution_db()
    record = await ContentApproval(db).ensure(await sequence_binding(db, "w", "l"))
    api = client(db, ws="other")
    assert api.get("/content-approvals").json()["items"] == []
    assert api.post(f"/content-approvals/{record['_id']}/decision", json={"decision": "approve", "revision": 1, "reviewed": True}).status_code == 404
    assert api.get(f"/content-approvals/{record['_id']}/audio").status_code == 404


@pytest.mark.asyncio
async def test_audio_preview_cannot_play_a_regenerated_clip(monkeypatch):
    db = execution_db()
    binding = await sequence_binding(db, "w", "l")
    binding["action"] = "voice_note"
    binding["context"]["voice_artifact_id"] = "artifact"
    binding["content"]["audio_digest"] = "old-hash"
    record = await ContentApproval(db).ensure(binding)
    monkeypatch.setattr("outreach.api.content_approvals.VoiceArtifacts.load", AsyncMock(return_value=b"RIFF-new-clip"))
    assert client(db).get(f"/content-approvals/{record['_id']}/audio").status_code == 409


def test_prepare_pagination_does_not_starve_later_leads():
    db = execution_db()
    base = db.outreach_leads.docs[0]
    db.outreach_leads.docs = [{**base, "id": f"lead-{n}"} for n in range(55)]
    api = client(db)
    first = api.post("/content-approvals/prepare/c?skip=0&limit=50").json()
    second = api.post(f"/content-approvals/prepare/c?skip={first['next_skip']}&limit=50").json()
    assert first["prepared"] == 50
    assert second["prepared"] == 5
    assert second["next_skip"] is None


@pytest.mark.asyncio
async def test_manual_review_can_revoke_renew_and_cancel_a_pending_reply():
    from outreach.core.manual_actions import ManualActions
    db = execution_db()
    await db.outreach_inbox_threads.insert_one({"id": "t", "workspace_id": "w", "account_id": "a", "conversation_urn": "urn:thread", "messages": [], "thread_revision": 1})
    job = await ManualActions(db).queue("j", "w", "a", "t", "inbox_reply", "reply", {"body": "Reviewed reply"}, "human")
    api = client(db)
    item = api.get("/content-approvals?view=history").json()["items"][0]
    assert item["current"] and item["can_cancel"]
    path = f"/content-approvals/{item['id']}"
    assert api.post(path + "/decision", json={"decision": "revoke", "revision": 2}).status_code == 200
    assert not await ContentApproval(db).allowed(job["binding"])
    assert api.post(path + "/decision", json={"decision": "approve", "revision": 3, "reviewed": True}).status_code == 200
    assert await ContentApproval(db).allowed(job["binding"])
    assert api.post(path + "/cancel").status_code == 200
    assert db.outreach_manual_actions.docs[0]["status"] == "cancelled"
    assert not db.outreach_inbox_threads.docs[0]["messages"]
    assert api.post(path + "/cancel").status_code == 409


@pytest.mark.asyncio
async def test_cached_voice_review_serves_exact_audio_and_tracks_voice_changes(monkeypatch):
    from cryptography.fernet import Fernet
    from outreach.core.voice_artifacts import VoiceArtifacts
    from outreach.core.voice_cloner import generate_mock_voice_wav
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    db = execution_db()
    db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"].update(type="voice_note", config={"script": "Hello"})
    from datetime import datetime, timezone
    from outreach.core.voice_studio import source_digest
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'local-provider-key')
    await db.outreach_voices.insert_one({'id': 'v', 'workspace_id': 'w', 'status': 'active', 'revision': 1,
        'elevenlabs_voice_id': 'real-voice', 'provider_source_digest': source_digest(),
        'consent': {'version': 1, 'actor': 'human', 'asserted_at': datetime.now(timezone.utc), 'assertion_digest': 'test-consent'}})
    api = client(db)
    assert api.post("/content-approvals/prepare/c").json()["voice_pending"] == 1
    base = await sequence_binding(db, "w", "l")
    recording = generate_mock_voice_wav()
    await VoiceArtifacts(db).store(base, recording)
    assert api.post("/content-approvals/prepare/c").json()["prepared"] == 1
    item = api.get("/content-approvals").json()["items"][0]
    assert item["has_audio"] and item["current"]
    path = f"/content-approvals/{item['id']}"
    audio = api.get(path + "/audio")
    assert audio.content == recording
    assert audio.headers["cache-control"] == "private, no-store"
    assert api.post(path + "/decision", json={"decision": "approve", "revision": 1, "reviewed": True}).status_code == 200
    await db.outreach_voices.update_one({"workspace_id": "w", "id": "v"}, {"$set": {"elevenlabs_voice_id": "changed-voice"}, "$inc": {"revision": 1}})
    assert api.post(path + "/decision", json={"decision": "approve", "revision": 2, "reviewed": True}).status_code == 409
