"""Disposable MongoDB tests: no real user data, provider requests or grants."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from tests.test_outreach_dispatch_authority import ready_db, dispatch

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Disposable replica set is opt-in")]


@pytest_asyncio.fixture
async def owned(ready_db):
    db, job = ready_db
    await db.workspaces.insert_one({"workspace_id": "w", "owner_id": "u"})
    await db.users.insert_one({"user_id": "u", "status": "active", "default_workspace_id": "shared"})
    await db.workspaces.insert_one({"workspace_id": "shared", "owner_id": "other"})
    await db.outreach_leads.insert_one({"workspace_id": "shared", "id": "protected", "email": "other@example.com"})
    return db, job


async def finish(db):
    from outreach.core.erasure import OutreachErasure
    service = OutreachErasure(db)
    inspected = await service.inspect("w")
    return await service.finish("w", "operator", "All workspace API, worker and integration writers were drained.",
        workers_drained=True, expected_digest=inspected["review_digest"])


async def test_request_stops_and_scrubs_credentials_before_any_content_deletion(owned):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    await db.outreach_mailboxes.insert_one({"workspace_id": "w", "sender_account_id": "a", "access_token_enc": "secret", "refresh_token_enc": "secret", "status": "active"})
    await db.outreach_connection_jobs.insert_one({"workspace_id": "w", "id": "pending", "li_at_enc": "secret", "jsession_id_enc": "secret", "li_a_enc": "secret", "status": "finalizing"})
    await db.outreach_voice_artifacts.insert_one({"workspace_id": "w", "audio_enc": "secret", "status": "prepared"})
    result = await OutreachErasure(db).request("w", "u")
    assert result["status"] == "awaiting_drain"
    assert await db.outreach_leads.find_one({"workspace_id": "w"})
    account = await db.outreach_accounts.find_one({"workspace_id": "w"})
    assert account["is_deleted"] and not account.get("session_cookie_enc")
    assert not (await db.outreach_mailboxes.find_one({"workspace_id": "w"})).get("refresh_token_enc")
    assert not (await db.outreach_connection_jobs.find_one({"workspace_id": "w"})).get("li_at_enc")
    assert not (await db.outreach_voice_artifacts.find_one({"workspace_id": "w"})).get("audio_enc")
    assert (await db.outreach_sender_execution.find_one({"workspace_id": "w"}))["permission"]["latched"]
    assert await db.outreach_leads.find_one({"workspace_id": "shared"})


async def test_request_requires_actual_workspace_ownership(owned):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    with pytest.raises(ValueError, match="owner"):
        await OutreachErasure(db).request("shared", "u")
    assert not await db.outreach_erasure_requests.find_one({"workspace_id": "shared"})


async def test_stop_blocks_suppression_writer_permission_payment_and_api(owned):
    from outreach.core.erasure import OutreachErasure, require_open_workspace
    from outreach.core.email_finder import suppress_email
    from outreach.core.suppression import SuppressionUnavailable
    from outreach.core.execution_permission import ExecutionPermission
    from outreach.core.paid_access import record_verified_payment
    from fastapi import HTTPException
    db, _ = owned
    await OutreachErasure(db).request("w", "u")
    with pytest.raises(SuppressionUnavailable):
        await suppress_email(db, workspace_id="w", email="lead@example.com", reason="stop")
    with pytest.raises(ValueError, match="erasure"):
        await ExecutionPermission(db).grant("w", "a", "g", ["engage"], "operator", clear_latch=True)
    with pytest.raises(ValueError, match="erasure"):
        await record_verified_payment(db, "w", "invoice", "operator", 1, datetime.now(timezone.utc) + timedelta(days=30))
    with pytest.raises(HTTPException) as error:
        await require_open_workspace({"user_id": "another", "default_workspace_id": "w"}, db)
    assert error.value.status_code == 409


async def test_erasure_stop_committed_before_final_dispatch_guard_prevents_http(owned, monkeypatch):
    from outreach.core.erasure import OutreachErasure
    from outreach.core.dispatch_authority import AuthorityDatabase
    from outreach.core.request_guard import RequestDenied
    db, job = owned
    seen, release = asyncio.Event(), asyncio.Event()
    original = AuthorityDatabase.fence_suppression
    once = False
    async def pause(self, workspace):
        nonlocal once
        if not once:
            once = True
            await self.database.outreach_accounts.find_one({"workspace_id": workspace}, session=self.session)
            seen.set()
            await release.wait()
        return await original(self, workspace)
    monkeypatch.setattr(AuthorityDatabase, "fence_suppression", pause)
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    work = asyncio.create_task(dispatch(db, job, factory))
    try:
        await asyncio.wait_for(seen.wait(), 5)
        await OutreachErasure(db).request("w", "u")
        release.set()
        with pytest.raises(RequestDenied):
            await asyncio.wait_for(work, 5)
        factory.assert_not_awaited()
    finally:
        release.set()
        await asyncio.gather(work, return_exceptions=True)


async def test_request_failure_rolls_back_guard_and_secret_scrub(owned, monkeypatch):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    original = OutreachErasure._stop
    async def fail(self, current, workspace, now):
        await original(self, current, workspace, now)
        raise RuntimeError("test-only failed stop")
    monkeypatch.setattr(OutreachErasure, "_stop", fail)
    with pytest.raises(RuntimeError):
        await OutreachErasure(db).request("w", "u")
    assert not await db.outreach_erasure_requests.find_one({"workspace_id": "w"})
    assert (await db.outreach_accounts.find_one({"workspace_id": "w"}))["session_cookie_enc"]
    assert not (await db.outreach_suppression_guards.find_one({"workspace_id": "w"})).get("erasure_state")


@pytest.mark.parametrize("drained,digest", [(False, "current"), (True, "stale")])
async def test_finish_requires_drain_and_current_inspection(owned, drained, digest):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    service = OutreachErasure(db)
    await service.request("w", "u")
    inspected = await service.inspect("w")
    with pytest.raises(ValueError):
        await service.finish("w", "operator", "All workspace writers drained for this request.", workers_drained=drained,
            expected_digest=inspected["review_digest"] if digest == "current" else "stale")
    assert await db.outreach_leads.find_one({"workspace_id": "w"})


async def test_finish_removes_content_and_retains_minimal_unknown_and_provider_holds(owned):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    await db.outreach_physical_requests.insert_one({"_id": "unknown", "workspace_id": "w", "sender_id": "a", "status": "unknown_outcome", "mutation": True,
        "response": {"body": "PRIVATE CONTENT"}, "error": "secret", "email": "private@example.com"})
    await db.outreach_proxy_inventory.update_one({"_id": "local-ip"}, {"$set": {"last_workspace_id": "w", "expires_at": datetime.now(timezone.utc) + timedelta(days=30), "password_enc": "secret"}})
    await db.outreach_do_not_contact.insert_one({"workspace_id": "w", "email": "private@example.com"})
    await OutreachErasure(db).request("w", "u")
    result = await finish(db)
    assert result["status"] == "erased"
    for name in ("outreach_accounts", "outreach_leads", "outreach_manual_actions", "outreach_do_not_contact", "outreach_physical_requests"):
        assert not await db[name].find_one({"workspace_id": "w"})
    holds = await db.outreach_erasure_holds.find({"workspace_id": "w"}).to_list(length=100)
    assert any(item["kind"] == "unresolved_submission" for item in holds)
    assert all("PRIVATE CONTENT" not in str(item) and "private@example.com" not in str(item) and "secret" not in str(item) for item in holds)
    inventory = await db.outreach_proxy_inventory.find_one({"_id": "local-ip"})
    assert inventory["status"] == "erasure_hold" and inventory["last_workspace_id"] == "w"
    assert not inventory.get("password_enc")
    assert await db.outreach_proxy_leases.find_one({"workspace_id": "w"})
    assert await db.outreach_leads.find_one({"workspace_id": "shared"})


async def test_repeated_finish_and_request_never_reopen_guard_or_duplicate_holds(owned):
    from outreach.core.erasure import OutreachErasure, workspace_is_open
    db, _ = owned
    service = OutreachErasure(db)
    await service.request("w", "u")
    await finish(db)
    count = await db.outreach_erasure_holds.count_documents({"workspace_id": "w"})
    assert (await finish(db))["status"] == "erased"
    assert (await service.request("w", "u"))["status"] == "erased"
    assert not await workspace_is_open(db, "w")
    assert await db.outreach_erasure_holds.count_documents({"workspace_id": "w"}) == count


async def test_unknown_outreach_collection_blocks_cleanup_without_false_completion(owned):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    await db.outreach_future_secret.insert_one({"workspace_id": "w", "secret": "private"})
    await OutreachErasure(db).request("w", "u")
    with pytest.raises(ValueError, match="collection"):
        await finish(db)
    assert await db.outreach_leads.find_one({"workspace_id": "w"})


async def test_user_manifest_includes_all_owned_workspaces_and_never_shared_default(owned):
    from outreach.core.erasure import begin_user_erasure
    db, _ = owned
    await db.workspaces.insert_one({"workspace_id": "second", "owner_id": "u"})
    await db.outreach_campaigns.insert_one({"workspace_id": "second", "id": "c2", "status": "active"})
    result = await begin_user_erasure(db, "u")
    assert set(result["owned_workspace_ids"]) == {"w", "second"}
    assert set(result["pending"]) == {"w", "second"}
    assert not await db.outreach_suppression_guards.find_one({"workspace_id": "shared"})


async def test_gdpr_worker_waits_for_outreach_drain_before_generic_deletion(owned, monkeypatch):
    from celery_workers.tasks import gdpr
    db, _ = owned
    monkeypatch.setenv("DB_NAME", db.name)
    monkeypatch.setattr(gdpr, "get_client", AsyncMock(return_value=db.client))
    result = await gdpr._async_erase("u", "shared")
    assert result["status"] == "pending_outreach_drain"
    assert await db.users.find_one({"user_id": "u"})
    assert await db.outreach_leads.find_one({"workspace_id": "shared"})


async def test_inspection_is_sanitized_and_changes_when_records_change(owned):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    service = OutreachErasure(db)
    await service.request("w", "u")
    first = await service.inspect("w")
    assert "session_cookie_enc" not in str(first) and "cipher" not in str(first)
    await db.outreach_leads.update_one({"workspace_id": "w"}, {"$set": {"email": "changed@example.com"}})
    second = await service.inspect("w")
    assert first["review_digest"] != second["review_digest"]
    assert "changed@example.com" not in str(second)


async def test_failed_batch_resumes_without_duplicating_evidence_or_erasing_other_tenant(owned, monkeypatch):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    service = OutreachErasure(db)
    await service.request("w", "u")
    original = OutreachErasure._erase_batch
    failed = False
    async def interrupt(self, current, workspace, name):
        nonlocal failed
        if name == "outreach_leads" and not failed:
            failed = True
            await original(self, current, workspace, name)
            raise RuntimeError("test-only interrupted batch")
        return await original(self, current, workspace, name)
    monkeypatch.setattr(OutreachErasure, "_erase_batch", interrupt)
    with pytest.raises(RuntimeError):
        await finish(db)
    assert (await db.outreach_erasure_requests.find_one({"workspace_id": "w"}))["status"] == "purging"
    assert await db.outreach_leads.find_one({"workspace_id": "w"})
    await finish(db)
    assert not await db.outreach_leads.find_one({"workspace_id": "w"})
    assert await db.outreach_leads.find_one({"workspace_id": "shared"})


async def test_cleanup_processes_more_than_one_batch(owned, monkeypatch):
    from outreach.core import erasure
    db, _ = owned
    monkeypatch.setattr(erasure, "BATCH_SIZE", 2)
    await db.outreach_leads.insert_many([{"workspace_id": "w", "id": f"lead-{i}"} for i in range(5)])
    await erasure.OutreachErasure(db).request("w", "u")
    await finish(db)
    assert not await db.outreach_leads.count_documents({"workspace_id": "w"})


async def test_empty_outreach_workspace_waits_for_drain_and_cleans_late_admitted_writer(owned):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    await db.workspaces.insert_one({"workspace_id": "empty", "owner_id": "u"})
    service = OutreachErasure(db)
    assert (await service.request("empty", "u"))["status"] == "awaiting_drain"
    await db.outreach_campaigns.insert_one({"workspace_id": "empty", "id": "late-writer", "status": "draft"})
    inspected = await service.inspect("empty")
    await service.finish("empty", "operator", "All previously admitted writers have completed and been drained.",
        workers_drained=True, expected_digest=inspected["review_digest"])
    assert not await db.outreach_campaigns.find_one({"workspace_id": "empty"})
    assert (await db.outreach_suppression_guards.find_one({"workspace_id": "empty"}))["erasure_state"] == "erased"


async def test_gdpr_completed_owned_erasure_keeps_shared_business_data(owned, monkeypatch):
    from celery_workers.tasks import gdpr
    from outreach.core.erasure import begin_user_erasure
    db, _ = owned
    await db.posts.insert_many([{"workspace_id": "w", "user_id": "u", "body": "Erase"},
        {"workspace_id": "shared", "user_id": "u", "body": "Shared"}])
    await begin_user_erasure(db, "u")
    await finish(db)
    monkeypatch.setenv("DB_NAME", db.name)
    monkeypatch.setattr(gdpr, "get_client", AsyncMock(return_value=db.client))
    result = await gdpr._async_erase("u", "shared")
    assert result["status"] == "completed"
    assert not await db.posts.find_one({"workspace_id": "w"})
    assert (await db.posts.find_one({"workspace_id": "shared"}))["body"] == "Shared"


async def test_private_cli_requires_exact_all_writer_acknowledgement(owned, capsys):
    from argparse import Namespace
    import json
    from outreach.core.erasure import OutreachErasure
    from outreach.ops.pilot import _run_db
    db, _ = owned
    await OutreachErasure(db).request("w", "u")
    await _run_db(Namespace(command="inspect-erasure", workspace="w"), db)
    digest = json.loads(capsys.readouterr().out)["review_digest"]
    args = Namespace(command="finish-erasure", workspace="w", operator="operator", evidence="All workspace writers have been drained.",
        review_digest=digest, workers_drained="I_PAUSED_AND_DRAINED_SENDER_WORKERS")
    with pytest.raises(ValueError, match="Drain"):
        await _run_db(args, db)
    args.workers_drained = "I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS"
    await _run_db(args, db)
    assert json.loads(capsys.readouterr().out)["status"] == "erased"


@pytest.mark.parametrize("kind", ["financial_reference", "unresolved_submission", "provider_term"])
async def test_retention_release_needs_fresh_review_and_provider_expiry(owned, kind):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    service = OutreachErasure(db)
    await service.request("w", "u")
    await finish(db)
    hold = {"_id": "review-hold", "workspace_id": "w", "kind": kind, "state": "held", "record_digest": "original",
        "asset_id": "asset", "expires_at": datetime.now(timezone.utc) + timedelta(days=1)}
    await db.outreach_erasure_holds.insert_one(hold)
    with pytest.raises(ValueError):
        await service.release_hold("w", "review-hold", "operator", "The retention basis was independently reviewed.", expected_digest="stale")
    inspected = await service.inspect_hold("w", "review-hold")
    if kind == "provider_term":
        with pytest.raises(ValueError, match="term"):
            await service.release_hold("w", "review-hold", "operator", "The provider term was independently reviewed.", expected_digest=inspected["review_digest"])
        await db.outreach_erasure_holds.update_one({"_id": "review-hold"}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(days=1)}})
        await db.outreach_proxy_inventory.insert_one({"_id": "asset", "workspace_id": "w",
            "status": "erasure_hold", "expires_at": datetime.now(timezone.utc) - timedelta(days=1)})
        inspected = await service.inspect_hold("w", "review-hold")
    await service.release_hold("w", "review-hold", "operator", "The retention basis was independently reviewed.", expected_digest=inspected["review_digest"])
    assert not await db.outreach_erasure_holds.find_one({"_id": "review-hold"})
    assert (await db.outreach_suppression_guards.find_one({"workspace_id": "w"}))["erasure_state"] == "erased"


async def test_retry_publisher_keeps_user_pending_when_broker_fails(owned, monkeypatch):
    from celery_workers.tasks import gdpr
    from outreach.core.erasure import begin_user_erasure
    db, _ = owned
    await begin_user_erasure(db, "u")
    monkeypatch.setenv("DB_NAME", db.name)
    monkeypatch.setattr(gdpr, "get_client", AsyncMock(return_value=db.client))
    monkeypatch.setattr(gdpr.celery_app, "send_task", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("test broker down")))
    assert (await gdpr._async_retry_erasure())["published"] == 0
    assert (await db.users.find_one({"user_id": "u"}))["status"] == "deletion_pending"
    assert (await db.users.find_one({"user_id": "u"})).get("deletion_next_publish_at")


async def test_oauth_callback_route_keeps_its_state_authentication_without_app_jwt(owned):
    from fastapi import FastAPI
    from db.mongo import get_db
    from outreach.api.router import router
    db, _ = owned
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local.test") as client:
        response = await client.get("/outreach/mailboxes/gmail/callback")
    assert response.status_code == 400


async def test_oauth_state_cannot_be_consumed_for_erasing_workspace(owned):
    from fastapi import HTTPException
    from outreach.core.erasure import OutreachErasure
    from outreach.core.mailbox_connection import consume_oauth_callback, _state_hash
    db, _ = owned
    await db.outreach_mailbox_oauth_states.insert_one({"_id": _state_hash("state"), "workspace_id": "w", "provider": "gmail",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10), "browser_binding_hash": _state_hash("nonce"), "code_verifier_enc": "secret", "job_id": "mailbox"})
    await OutreachErasure(db).request("w", "u")
    with pytest.raises(HTTPException) as error:
        await consume_oauth_callback(db, "gmail", "state", "code", browser_binding_nonce="nonce")
    assert error.value.status_code == 409
    # A denied callback preserves the stopped tenant's unconsumed state for
    # drained erasure; it never deletes outside the workspace transaction.
    state = await db.outreach_mailbox_oauth_states.find_one({"_id": _state_hash("state")})
    assert state and not state.get('code_verifier_enc')


async def test_public_api_key_dependencies_reject_closed_workspace_even_if_key_restored(owned, monkeypatch):
    import hashlib
    from fastapi import HTTPException, Response
    from starlette.requests import Request
    from outreach.api import integrations
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    key = "unr_live_" + "x" * 36
    await db.outreach_api_keys.insert_one({"_id": "key", "workspace_id": "w", "key_hash": hashlib.sha256(key.encode()).hexdigest(), "scopes": ["leads:read"]})
    await OutreachErasure(db).request("w", "u")
    assert (await db.outreach_api_keys.find_one({"_id": "key"})).get("revoked_at")
    await db.outreach_api_keys.update_one({"_id": "key"}, {"$unset": {"revoked_at": ""}})
    monkeypatch.setattr(integrations, "is_integrations_pilot_allowed", lambda _: True)
    with pytest.raises(HTTPException) as error:
        await integrations.authenticate_api_key(authorization=None, x_api_key=key, db=db)
    assert error.value.status_code == 409
    request = Request({"type": "http", "headers": [], "query_string": b""})
    with pytest.raises(HTTPException) as error:
        await integrations.require_api_key_scope("leads:read")(request, Response(), authorization=None, x_api_key=key, db=db)
    assert error.value.status_code == 409


async def test_copied_webhook_credentials_are_scrubbed_and_new_delivery_reads_never_send(owned):
    from outreach.core.erasure import OutreachErasure
    from outreach.core.webhook_delivery import dispatch_due_deliveries
    db, _ = owned
    await db.outreach_webhook_deliveries.insert_one({"id": "delivery", "workspace_id": "w", "event_id": "event", "status": "pending",
        "secret_enc": "secret", "target_url_enc": "secret", "target_url": "https://example.com/hook", "lease_id": None,
        "next_attempt_at": datetime.now(timezone.utc) - timedelta(minutes=1), "attempt": 0})
    await OutreachErasure(db).request("w", "u")
    delivery = await db.outreach_webhook_deliveries.find_one({"id": "delivery"})
    assert not delivery.get("secret_enc") and not delivery.get("target_url_enc")
    await db.outreach_webhook_deliveries.update_one({"id": "delivery"}, {"$set": {"status": "pending"}})
    client = AsyncMock()
    await dispatch_due_deliveries(db, safe_client=client)
    client.post.assert_not_awaited()


@pytest.mark.parametrize("legacy_shape", ["user_workspace", "user_only"])
async def test_legacy_personal_scope_is_owned_stopped_and_erased_without_touching_shared_rows(owned, legacy_shape):
    from outreach.core.erasure import begin_user_erasure, OutreachErasure
    db, _ = owned
    row = {"user_id": "u", "content": "Legacy private prompt"}
    if legacy_shape == "user_workspace":
        row["workspace_id"] = "u"
    await db.outreach_ai_prompts.insert_one(row)
    await db.outreach_ai_prompts.insert_one({"user_id": "u", "workspace_id": "shared", "content": "Team prompt"})
    manifest = await begin_user_erasure(db, "u")
    assert set(manifest["owned_workspace_ids"]) == {"w", "u"}
    assert (await db.outreach_suppression_guards.find_one({"workspace_id": "u"}))["erasure_state"] == "stopped"
    service = OutreachErasure(db)
    inspected = await service.inspect("u")
    await service.finish("u", "operator", "All legacy personal scope writers were drained.", workers_drained=True, expected_digest=inspected["review_digest"])
    assert not await db.outreach_ai_prompts.find_one({"workspace_id": "u"})
    assert (await db.outreach_ai_prompts.find_one({"workspace_id": "shared"}))["content"] == "Team prompt"


async def test_manifest_overflow_refuses_completion_instead_of_truncating(owned):
    from outreach.core.erasure import begin_user_erasure
    db, _ = owned
    await db.workspaces.insert_many([{"workspace_id": f"extra-{i}", "owner_id": "u"} for i in range(1000)])
    with pytest.raises(ValueError, match="capacity"):
        await begin_user_erasure(db, "u")
    assert await db.users.find_one({"user_id": "u"})


async def test_deleted_identity_cannot_bootstrap_a_new_user_from_cached_claims(owned):
    from api.deps import _bootstrap_user_from_claims
    from fastapi import HTTPException
    from outreach.core.erasure import begin_user_erasure
    db, _ = owned
    await db.users.update_one({"user_id": "u"}, {"$set": {"firebase_uid": "firebase-u"}})
    await begin_user_erasure(db, "u")
    await db.users.delete_one({"user_id": "u"})
    with pytest.raises(HTTPException) as error:
        await _bootstrap_user_from_claims(db, {"uid": "firebase-u", "email": "deleted@example.com"})
    assert error.value.status_code == 403
    assert not await db.users.find_one({"firebase_uid": "firebase-u"})


@pytest.mark.parametrize("failure", ["storage", "firebase", "stripe_config"])
async def test_external_cleanup_failure_keeps_pending_user_and_retry_references(owned, monkeypatch, failure):
    from celery_workers.tasks import gdpr
    from outreach.core.erasure import begin_user_erasure
    db, _ = owned
    if failure == "storage":
        await db.media_assets.insert_one({"workspace_id": "w", "url": "https://example.com/private-file"})
        monkeypatch.setattr("utils.storage.delete_file_async", AsyncMock(side_effect=RuntimeError("test storage down")))
    elif failure == "firebase":
        await db.users.update_one({"user_id": "u"}, {"$set": {"firebase_uid": "firebase-u"}})
        monkeypatch.setattr("api.deps.get_firebase_app", lambda: None)
        monkeypatch.setattr("firebase_admin.auth.delete_user", lambda _: (_ for _ in ()).throw(RuntimeError("test Firebase down")))
    else:
        await db.users.update_one({"user_id": "u"}, {"$set": {"stripe_subscription_id": "subscription-u"}})
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    await begin_user_erasure(db, "u")
    await finish(db)
    monkeypatch.setenv("DB_NAME", db.name)
    monkeypatch.setattr(gdpr, "get_client", AsyncMock(return_value=db.client))
    result = await gdpr._async_erase("u", "shared")
    assert result["status"] == "pending_external_cleanup"
    user = await db.users.find_one({"user_id": "u"})
    assert user and user["status"] == "deletion_pending"
    if failure == "storage":
        assert await db.media_assets.find_one({"workspace_id": "w"})
    if failure == "firebase":
        assert user["firebase_uid"] == "firebase-u"
    if failure == "stripe_config":
        assert user["stripe_subscription_id"] == "subscription-u"


@pytest.mark.parametrize("collection,record", [
    ("outreach_intents", {"status": "pending"}),
    ("outreach_email_operations", {"status": "accepted", "accepted_at": datetime.now(timezone.utc)}),
    ("outreach_connection_jobs", {"status": "completed", "finalization_prepared": True, "connection_cleanup_complete": True}),
])
async def test_known_noncalls_and_completed_work_are_not_retained_as_unknown(owned, collection, record):
    from outreach.core.erasure import OutreachErasure
    from outreach.core.authorization import canonical_hash
    db, _ = owned
    await db[collection].insert_one({"_id": "known-record", "workspace_id": "w", **record})
    await OutreachErasure(db).request("w", "u")
    await finish(db)
    assert not await db.outreach_erasure_holds.find_one({"workspace_id": "w", "source_collection": collection,
        "record_id_hash": canonical_hash("known-record")})


async def test_retained_received_outcome_keeps_acceptance_label_without_content(owned):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    await db.outreach_physical_requests.insert_one({"_id": "received", "workspace_id": "w", "status": "response_received",
        "mutation": True, "provider_outcome": {"status": "accepted", "body": "PRIVATE CONTENT"}})
    await OutreachErasure(db).request("w", "u")
    await finish(db)
    hold = await db.outreach_erasure_holds.find_one({"workspace_id": "w", "source_collection": "outreach_physical_requests"})
    assert hold["kind"] == "submission_receipt" and hold["outcome_state"] == "accepted"
    assert "PRIVATE CONTENT" not in str(hold)


async def test_manifest_failure_leaves_durable_pending_user_for_publication_retry(owned, monkeypatch):
    from api.routes.user import delete_account
    from fastapi import HTTPException
    from starlette.requests import Request
    db, _ = owned
    monkeypatch.setattr("outreach.core.erasure.begin_user_erasure", AsyncMock(side_effect=RuntimeError("test discovery failure")))
    enqueue = AsyncMock()
    monkeypatch.setattr("api.routes.user.enqueue_task", enqueue)
    request = Request({"type": "http", "method": "DELETE", "path": "/api/user/account", "headers": [],
        "query_string": b"", "client": ("test-erasure-" + db.name, 12345)})
    with pytest.raises(HTTPException) as error:
        await delete_account(request=request, current_user={"user_id": "u", "firebase_uid": "firebase-u"}, db=db)
    assert error.value.status_code == 503
    user = await db.users.find_one({"user_id": "u"})
    assert user["status"] == "deletion_pending" and user["deletion_next_publish_at"]
    enqueue.assert_not_called()


async def test_bootstrap_insert_race_removes_only_new_deleted_identity_profile(owned, monkeypatch):
    from api.deps import _bootstrap_user_from_claims
    from fastapi import HTTPException
    db, _ = owned
    guard = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr("outreach.core.erasure.identity_is_erased", guard)
    with pytest.raises(HTTPException) as error:
        await _bootstrap_user_from_claims(db, {"uid": "race-u", "email": "race@example.com"})
    assert error.value.status_code == 403
    assert not await db.users.find_one({"firebase_uid": "race-u"})
    assert await db.users.find_one({"user_id": "u"})


@pytest.mark.parametrize("provider", ["firebase_auth", "firebase_storage"])
async def test_already_absent_external_resource_completes_retry(owned, monkeypatch, provider):
    from celery_workers.tasks import gdpr
    from outreach.core.erasure import begin_user_erasure
    db, _ = owned
    if provider == "firebase_auth":
        from firebase_admin.auth import UserNotFoundError
        await db.users.update_one({"user_id": "u"}, {"$set": {"firebase_uid": "firebase-u"}})
        monkeypatch.setattr("api.deps.get_firebase_app", lambda: None)
        monkeypatch.setattr("firebase_admin.auth.delete_user", lambda _: (_ for _ in ()).throw(UserNotFoundError("Already removed")))
    else:
        from google.api_core.exceptions import NotFound
        await db.media_assets.insert_one({"workspace_id": "w", "url": "https://example.com/private-file"})
        monkeypatch.setattr("utils.storage.delete_file_async", AsyncMock(side_effect=NotFound("Already removed")))
    await begin_user_erasure(db, "u")
    await finish(db)
    monkeypatch.setenv("DB_NAME", db.name)
    monkeypatch.setattr(gdpr, "get_client", AsyncMock(return_value=db.client))
    assert (await gdpr._async_erase("u", "shared"))["status"] == "completed"
    assert not await db.users.find_one({"user_id": "u"})


@pytest.mark.parametrize("asset_state", ["missing", "other_workspace", "renewed"])
async def test_provider_hold_release_requires_current_owned_expired_asset(owned, asset_state):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    service = OutreachErasure(db)
    await service.request("w", "u")
    await finish(db)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    await db.outreach_erasure_holds.insert_one({"_id": "term-review", "workspace_id": "w", "kind": "provider_term",
        "asset_id": "term-asset", "expires_at": past, "state": "held"})
    if asset_state != "missing":
        await db.outreach_proxy_inventory.insert_one({"_id": "term-asset", "last_workspace_id": "shared" if asset_state == "other_workspace" else "w",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1) if asset_state == "renewed" else past})
    inspected = await service.inspect_hold("w", "term-review")
    with pytest.raises(ValueError):
        await service.release_hold("w", "term-review", "operator", "Current provider ownership and expiry were reviewed.", expected_digest=inspected["review_digest"])
    assert await db.outreach_erasure_holds.find_one({"_id": "term-review"})


@pytest.mark.parametrize("provider", ["stripe", "razorpay"])
@pytest.mark.parametrize("scenario", ["already_cancelled", "cancel_lost_ack", "wrong_identity", "missing"])
async def test_subscription_cleanup_retries_from_proven_provider_state(owned, monkeypatch, provider, scenario):
    from celery_workers.tasks import gdpr
    from outreach.core.erasure import begin_user_erasure
    from unittest.mock import Mock
    db, _ = owned
    sub_id = "test-subscription-u"
    field = provider + "_subscription_id"
    await db.users.update_one({"user_id": "u"}, {"$set": {field: sub_id}})
    cancelled = "canceled" if provider == "stripe" else "cancelled"
    fetched = {"id": "other" if scenario == "wrong_identity" else sub_id,
        "status": "active" if scenario == "cancel_lost_ack" else cancelled}
    read = Mock(side_effect=RuntimeError("test missing resource") if scenario == "missing" else None, return_value=fetched)
    cancel = Mock(side_effect=RuntimeError("test lost acknowledgement") if scenario == "cancel_lost_ack" else None,
        return_value={"id": sub_id, "status": cancelled})
    if provider == "stripe":
        monkeypatch.setenv("STRIPE_SECRET_KEY", "test-only")
        monkeypatch.setattr("stripe.Subscription.retrieve", read)
        monkeypatch.setattr("stripe.Subscription.cancel", cancel)
        monkeypatch.setattr("stripe.Subscription.delete", lambda *_: (_ for _ in ()).throw(AssertionError("Legacy delete transport is blocked in this test")))
    else:
        monkeypatch.setenv("RAZORPAY_KEY_ID", "test-only")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "test-only")
        client = Mock()
        client.subscription.fetch = read
        client.subscription.cancel = cancel
        import sys
        from types import SimpleNamespace
        monkeypatch.setitem(sys.modules, "razorpay", SimpleNamespace(Client=lambda **_: client))
    await begin_user_erasure(db, "u")
    await finish(db)
    monkeypatch.setenv("DB_NAME", db.name)
    monkeypatch.setattr(gdpr, "get_client", AsyncMock(return_value=db.client))
    first = await gdpr._async_erase("u", "shared")
    if scenario == "already_cancelled":
        assert first["status"] == "completed"
        cancel.assert_not_called()
    else:
        assert first["status"] == "pending_external_cleanup"
        assert (await db.users.find_one({"user_id": "u"}))[field] == sub_id
        if scenario == "cancel_lost_ack":
            read.return_value = {"id": sub_id, "status": cancelled}
            assert (await gdpr._async_erase("u", "shared"))["status"] == "completed"
            assert cancel.call_count == 1
        else:
            cancel.assert_not_called()


async def test_closed_workspace_cannot_import_fresh_proxy_credentials(owned):
    from outreach.core.erasure import OutreachErasure
    from outreach.core.managed_proxy import import_iproyal_proxy
    from outreach.core.suppression import SuppressionUnavailable
    db, _ = owned
    await OutreachErasure(db).request("w", "u")
    await finish(db)
    with pytest.raises(SuppressionUnavailable):
        await import_iproyal_proxy(db, "http://test-user:test-password@191.116.125.248:23456", "IN", "test-order", "w",
            datetime.now(timezone.utc) + timedelta(days=30))
    assert not await db.outreach_proxy_inventory.find_one({"provider_order_id": "test-order"})


async def test_late_writer_after_partial_batch_can_be_removed_on_fresh_drained_retry(owned, monkeypatch):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    service = OutreachErasure(db)
    await service.request("w", "u")
    original = OutreachErasure._erase_batch
    once = False
    async def late(self, current, workspace, name):
        nonlocal once
        result = await original(self, current, workspace, name)
        if name == "outreach_templates" and not once:
            once = True
            await current.outreach_leads.insert_one({"workspace_id": "w", "id": "late", "email": "late@example.com"})
        return result
    monkeypatch.setattr(OutreachErasure, "_erase_batch", late)
    with pytest.raises(ValueError, match="incomplete"):
        await finish(db)
    assert await db.outreach_leads.find_one({"id": "late"})
    await finish(db)
    assert not await db.outreach_leads.find_one({"id": "late"})


@pytest.mark.parametrize("saved", [None, {}])
async def test_deletion_status_never_claims_completion_without_recorded_evidence(owned, saved):
    from api.routes.user import get_data_deletion_status
    from starlette.requests import Request
    db, _ = owned
    if saved is not None:
        await db.data_deletions.insert_one({"confirmation_code": "test-code", **saved})
    request = Request({"type": "http", "method": "GET", "path": "/api/user/data-deletion-status/test-code", "headers": [],
        "query_string": b"", "client": ("test-deletion-status-" + db.name, 12345)})
    result = await get_data_deletion_status(request=request, confirmation_code="test-code", db=db)
    assert result["status"] == ("not_found" if saved is None else "unknown")
    assert "purged" not in result["details"]
    assert result["created_at"] is None


async def test_erased_invoice_cannot_be_applied_to_another_workspace_even_after_hold_release(owned):
    from outreach.core.erasure import OutreachErasure
    from outreach.core.paid_access import record_verified_payment
    db, _ = owned
    term = datetime.now(timezone.utc) + timedelta(days=30)
    await db.outreach_payment_receipts.insert_one({"_id": "test-verified-invoice", "workspace_id": "w", "seats": 1, "paid_through": term})
    service = OutreachErasure(db)
    await service.request("w", "u")
    await finish(db)
    hold = await db.outreach_erasure_holds.find_one({"workspace_id": "w", "source_collection": "outreach_payment_receipts"})
    inspected = await service.inspect_hold("w", hold["_id"])
    await service.release_hold("w", hold["_id"], "operator", "The financial retention basis was independently reviewed.", expected_digest=inspected["review_digest"])
    await db.outreach_access_requests.insert_one({"workspace_id": "new-fixture", "country_code": "IN", "seats": 1})
    await db.outreach_proxy_inventory.insert_one({"_id": "new-fixture-ip", "last_workspace_id": "new-fixture", "country_code": "IN",
        "status": "available", "expires_at": term + timedelta(days=1)})
    with pytest.raises(ValueError, match="Invoice"):
        await record_verified_payment(db, "new-fixture", "test-verified-invoice", "test-operator", 1, term)
    assert not await db.outreach_entitlements.find_one({"workspace_id": "new-fixture"})


async def test_concurrent_invoice_digest_claims_bind_only_one_workspace(owned):
    from outreach.core.paid_access import claim_invoice_reference
    db, _ = owned
    term = datetime.now(timezone.utc) + timedelta(days=30)
    results = await asyncio.gather(claim_invoice_reference(db, "fixture-invoice", "w", 1, term),
        claim_invoice_reference(db, "fixture-invoice", "other", 1, term), return_exceptions=True)
    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1
    row = await db.account_invoice_guards.find_one({})
    assert set(row) == {"_id", "binding_digest"}
    assert "fixture-invoice" not in str(row)


@pytest.mark.parametrize("tombstone", [False, True])
async def test_duplicate_profile_insert_recovery_rechecks_deletion_authority(owned, monkeypatch, tombstone):
    from api.deps import _bootstrap_user_from_claims
    from fastapi import HTTPException
    from pymongo.errors import DuplicateKeyError
    from types import SimpleNamespace
    db, _ = owned
    users = SimpleNamespace(find_one=AsyncMock(side_effect=[None, None, {"user_id": "raced", "status": "deletion_pending"}]),
        insert_one=AsyncMock(side_effect=DuplicateKeyError("test concurrent profile")))
    wrapped = SimpleNamespace(users=users)
    monkeypatch.setattr("outreach.core.erasure.identity_is_erased", AsyncMock(side_effect=[False, tombstone]))
    with pytest.raises(HTTPException) as error:
        await _bootstrap_user_from_claims(wrapped, {"uid": "raced", "email": "race@example.com"})
    assert error.value.status_code == 403
    assert await db.users.find_one({"user_id": "u"})


async def test_fresh_drained_finish_rechecks_previously_erased_workspace(owned):
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    service = OutreachErasure(db)
    await service.request("w", "u")
    await finish(db)
    await db.outreach_leads.insert_one({"workspace_id": "w", "id": "unexpected-legacy-writer"})
    assert (await service.request("w", "u"))["status"] == "awaiting_drain"
    await finish(db)
    assert not await db.outreach_leads.find_one({"id": "unexpected-legacy-writer"})


async def test_actual_payment_with_submillisecond_term_remains_erasable_after_bson_roundtrip(owned):
    from outreach.core.paid_access import record_verified_payment
    from outreach.core.erasure import OutreachErasure
    db, _ = owned
    term = (datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=123456)
    await db.outreach_access_requests.update_one({"workspace_id": "w"}, {"$set": {"seats": 1, "country_code": "IN"}}, upsert=True)
    await db.outreach_proxy_inventory.insert_one({"_id": "term-test-ip", "last_workspace_id": "w", "country_code": "IN",
        "status": "available", "expires_at": term + timedelta(days=1)})
    await record_verified_payment(db, "w", "test-ms-invoice", "test-operator", 1, term)
    receipt = await db.outreach_payment_receipts.find_one({"_id": "test-ms-invoice"})
    assert receipt["paid_through"].microsecond == 123000
    await OutreachErasure(db).request("w", "u")
    assert (await finish(db))["status"] == "erased"
    assert not await db.outreach_payment_receipts.find_one({"_id": "test-ms-invoice"})
