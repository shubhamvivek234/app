"""Exact content decisions never substitute for campaign or execution permission."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from tests.outreach_memory import Database
from outreach.core.content_approval import ContentApproval, make_binding

NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)


def binding(**changes):
    values = dict(workspace_id="w", account={"id": "a", "workspace_id": "w", "credential_generation": "g"},
                  source="sequence", recipient="urn:li:person:r", action="send_message", content={"body": "Hello"},
                  context={"campaign_id": "c", "lead_id": "l", "enrollment_id": "e", "node_id": "n",
                           "sequence_version": 1, "authorization_revision": 2, "sequence_digest": "dag"})
    values.update(changes)
    return make_binding(**values)


@pytest.mark.asyncio
async def test_exact_approval_has_actor_expiry_and_no_execution_grant():
    db = Database()
    service = ContentApproval(db)
    value = binding()
    record = await service.ensure(value, now=NOW)
    assert record["status"] == "pending"
    assert not await service.allowed(value, now=NOW)
    await service.decide("w", record["_id"], "reviewer", "approve", revision=record["revision"], now=NOW)
    assert await service.allowed(value, now=NOW)
    assert not await service.allowed(value, now=NOW + timedelta(days=1))
    assert db.outreach_content_approvals.docs[0]["history"][0]["actor_id"] == "reviewer"
    assert not db.outreach_sender_execution.docs
    assert not db.outreach_execution_permissions.docs


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["workspace_id", "sender_id", "credential_generation", "recipient", "action", "source", "content", "context", "policy_version", "policy_digest"])
async def test_binding_changes_never_reuse_approval(field):
    db = Database()
    original = binding()
    service = ContentApproval(db)
    record = await service.ensure(original, now=NOW)
    await service.decide("w", record["_id"], "reviewer", "approve", revision=1, now=NOW)
    changed = deepcopy(original)
    changed[field] = {"body": "Different"} if field == "content" else {"node_id": "different"} if field == "context" else "different"
    assert not await service.allowed(changed, now=NOW)


@pytest.mark.asyncio
async def test_stale_decision_and_cross_workspace_decision_rejected():
    db = Database()
    service = ContentApproval(db)
    record = await service.ensure(binding(), now=NOW)
    with pytest.raises(ValueError):
        await service.decide("other", record["_id"], "reviewer", "approve", revision=1, now=NOW)
    await service.decide("w", record["_id"], "reviewer", "reject", revision=1, now=NOW)
    with pytest.raises(ValueError):
        await service.decide("w", record["_id"], "reviewer", "approve", revision=1, now=NOW)
    assert not await service.allowed(binding(), now=NOW)


@pytest.mark.asyncio
async def test_revocation_is_preserved_by_worker_ensure():
    db = Database()
    service = ContentApproval(db)
    record = await service.ensure(binding(), now=NOW)
    await service.decide("w", record["_id"], "reviewer", "approve", revision=1, now=NOW)
    await service.decide("w", record["_id"], "reviewer", "revoke", revision=2, now=NOW)
    assert (await service.ensure(binding(), now=NOW))["status"] == "revoked"
    assert not await service.allowed(binding(), now=NOW)


@pytest.mark.asyncio
async def test_anonymous_actor_cannot_approve():
    service = ContentApproval(Database())
    record = await service.ensure(binding(), now=NOW)
    with pytest.raises(ValueError):
        await service.decide("w", record["_id"], "", "approve", revision=1, now=NOW)


def test_canonical_content_framing_avoids_concatenation_collisions():
    from outreach.core.authorization import canonical_hash
    assert canonical_hash(binding(recipient="ab", content={"body": "c"})) != canonical_hash(binding(recipient="a", content={"body": "bc"}))


@pytest.mark.asyncio
async def test_email_review_includes_effective_footer_and_mailbox_identity():
    from outreach.core.content_approval import sequence_binding
    from outreach.core.mailbox_delivery import _mime_message
    from email import message_from_bytes, policy
    from tests.test_outreach_execution_outbox import execution_db
    db = execution_db()
    db.outreach_leads.docs[0]["email"] = "ADA@example.com"
    node = db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"]
    node.update(type="send_email", config={"subject": " Hello ", "body": "Reviewed email"})
    await db.outreach_mailboxes.insert_one({"workspace_id": "w", "sender_account_id": "a", "email": "sender@example.com", "provider": "gmail", "connection_job_id": "generation-1"})
    value = await sequence_binding(db, "w", "l")
    mime = message_from_bytes(_mime_message("sender@example.com", "ada@example.com", "Hello", "Reviewed email", "m"), policy=policy.default)
    assert value["content"]["body"] == mime.get_content().replace("\r\n", "\n")
    assert value["content"]["sender_email"] == "sender@example.com"
    assert value["recipient"] == "ada@example.com"
    db.outreach_mailboxes.docs[0]["connection_job_id"] = "generation-2"
    assert (await sequence_binding(db, "w", "l"))["context"] != value["context"]


@pytest.mark.asyncio
async def test_sequence_waits_for_exact_review_before_submission(monkeypatch):
    from tests.test_outreach_execution_outbox import execution_db, stub_transport
    executor, client = stub_transport(monkeypatch, review_content=True)
    db = execution_db()
    result = await executor.SequenceExecutor.execute_lead_step("l", db, workspace_id="w")
    assert result["status"] == "content_approval_required"
    assert result["not_submitted"]
    client.send_direct_message.assert_not_awaited()
    assert not db.outreach_intents.docs[0].get("attempt")
    approval = db.outreach_content_approvals.docs[0]
    assert approval["binding"]["content"] == {"body": "Hello"}
    await ContentApproval(db).decide("w", approval["_id"], "reviewer", "approve", revision=1)
    db.outreach_intents.docs[0]["next_action_due_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert (await executor.SequenceExecutor.execute_lead_step("l", db, workspace_id="w"))["status"] != "content_approval_required"
    client.send_direct_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_personalization_edit_and_final_revocation_block_approved_send(monkeypatch):
    from tests.test_outreach_execution_outbox import execution_db, stub_transport
    executor, client = stub_transport(monkeypatch, review_content=True)
    db = execution_db()
    db.outreach_leads.docs[0]["first_name"] = "Ada"
    db.outreach_sequences.docs[0]["compiled_dag"]["nodes"]["n"]["config"]["body"] = "Hello {{first_name}}"
    await executor.SequenceExecutor.execute_lead_step("l", db, workspace_id="w")
    original = db.outreach_content_approvals.docs[0]
    await ContentApproval(db).decide("w", original["_id"], "reviewer", "approve", revision=1)
    db.outreach_leads.docs[0]["first_name"] = "Grace"
    db.outreach_intents.docs[0]["next_action_due_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert (await executor.SequenceExecutor.execute_lead_step("l", db, workspace_id="w"))["status"] == "content_approval_required"
    client.send_direct_message.assert_not_awaited()
    changed = db.outreach_content_approvals.docs[1]
    assert changed["binding"]["content"]["body"] == "Hello Grace"
    await ContentApproval(db).decide("w", changed["_id"], "reviewer", "approve", revision=1)
    db.outreach_intents.docs[0]["next_action_due_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    update = db.outreach_tasks.update_one
    async def revoke_after_evidence(query, changes, **kwargs):
        result = await update(query, changes, **kwargs)
        if changes.get("$set", {}).get("status") == "dispatching":
            await ContentApproval(db).decide("w", changed["_id"], "reviewer", "revoke", revision=2)
        return result
    monkeypatch.setattr(db.outreach_tasks, "update_one", revoke_after_evidence)
    assert (await executor.SequenceExecutor.execute_lead_step("l", db, workspace_id="w"))["status"] == "content_approval_required"
    client.send_direct_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_actual_adapter_arguments_cannot_substitute_unreviewed_text():
    from unittest.mock import AsyncMock
    from outreach.engine.voyager_client import VoyagerClient
    from outreach.core.request_guard import RequestEnvelope, RequestDenied
    client = object.__new__(VoyagerClient)
    client.is_mock = False
    client.request_envelope = RequestEnvelope(Database(), "w", "a", "g", "sequence", "http://proxy:8000", approval_binding=binding())
    client._resolve_profile_urn = AsyncMock(return_value=None)
    with pytest.raises(RequestDenied):
        await client.send_direct_message("urn:li:person:r", "Unreviewed body")
    client._resolve_profile_urn.assert_not_awaited()


@pytest.mark.asyncio
async def test_voice_artifact_is_encrypted_and_digest_verified(monkeypatch):
    from outreach.core.voice_artifacts import VoiceArtifacts
    from outreach.core.voice_cloner import generate_mock_voice_wav
    from cryptography.fernet import Fernet
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    db = Database()
    service = VoiceArtifacts(db)
    value = binding(action="voice_note", content={"body": "Hello", "voice_id": "v"})
    audio = generate_mock_voice_wav()
    first = await service.store(value, audio, now=NOW)
    assert first["audio_enc"] != audio.decode("latin1")
    assert await service.load("w", first["_id"], now=NOW) == audio
    db.outreach_voice_artifacts.docs[0]["audio_digest"] = "tampered"
    with pytest.raises(ValueError):
        await service.load("w", first["_id"], now=NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize("action,source,path", [("message", "sequence", "/voyager/api/messaging/dash/messengerMessages"), ("like", "engage", "/voyager/api/feed/reactions")])
async def test_approval_revoked_during_final_sender_write_denies_factory(monkeypatch, action, source, path):
    from unittest.mock import AsyncMock
    from tests.test_outreach_request_guard import ready_envelope, NOW as request_now
    from outreach.core.request_guard import RequestEnvelope, RequestDenied
    validate_content, authorize_content = RequestEnvelope._validate_content, RequestEnvelope._authorize_content
    db, envelope = await ready_envelope(monkeypatch, source=source)
    value = binding(source=source, action="like" if action == "like" else "send_message",
                    content={"reaction": "LIKE"} if action == "like" else {"body": "Hello"})
    envelope.approval_binding = value
    envelope._validate_content = validate_content.__get__(envelope)
    envelope._authorize_content = authorize_content.__get__(envelope)
    record = await ContentApproval(db).ensure(value, now=request_now)
    await ContentApproval(db).decide("w", record["_id"], "reviewer", "approve", revision=1, now=request_now)
    write = db.outreach_sender_execution.find_one_and_update
    async def revoke_after_sender_cas(query, update, **kwargs):
        result = await write(query, update, **kwargs)
        if update.get("$set", {}).get("physical_request_token"):
            await ContentApproval(db).decide("w", record["_id"], "reviewer", "revoke", revision=2, now=request_now)
        return result
    monkeypatch.setattr(db.outreach_sender_execution, "find_one_and_update", revoke_after_sender_cas)
    factory = AsyncMock()
    with pytest.raises(RequestDenied, match="content_approval_required"):
        await envelope.call("POST", path, factory, action=action, now=request_now)
    factory.assert_not_awaited()
    assert db.outreach_physical_requests.docs[0]["status"] == "not_submitted"
