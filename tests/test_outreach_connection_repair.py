"""Account-local credential fence and drained finalization repair."""
from datetime import datetime, timedelta, timezone

import pytest

from outreach.core.connection_repair import ConnectionRepair, credential_deadline
from tests.outreach_memory import Database

NOW = datetime.now(timezone.utc)

def database():
    return Database(outreach_connection_jobs=[{"id": "j", "workspace_id": "w", "sender_id": "a", "user_id": "u",
        "status": "running", "verification_owner_token": "owner", "created_at": NOW, "custody_expires_at": NOW + timedelta(minutes=15),
        "proxy_id": "ip", "country_code": "IN", "new_proxy_reservation": True, "created_slot": True, "li_at_enc": "cipher", "jsession_id_enc": "cipher"}],
        outreach_connection_locks=[{"_id": "a", "workspace_id": "w", "job_id": "j"}],
        outreach_sender_slots=[{"_id": "slot", "workspace_id": "w", "sender_id": "a", "reservation_job_id": "j"}],
        outreach_proxy_leases=[{"_id": "ip", "workspace_id": "w", "sender_id": "a", "reservation_job_id": "j"}],
        outreach_proxy_inventory=[{"_id": "ip", "status": "available", "last_workspace_id": "w", "country_code": "IN", "expires_at": NOW + timedelta(days=1)}])

async def prepared(db):
    job = await db.outreach_connection_jobs.find_one({"id": "j"})
    service = ConnectionRepair(db)
    await service.prepare(job, "owner", "g", {"account_name": "Sender", "linkedin_urn": "urn:sender"}, now=NOW)
    await db.outreach_connection_jobs.update_one({"id": "j"}, {"$set": {"status": "finalizing", "credential_generation": "g", "expected_linkedin_urn": "urn:sender"}})
    return service, await db.outreach_connection_jobs.find_one({"id": "j"})

@pytest.mark.asyncio
async def test_expiry_closes_account_fence_and_blocks_cached_credentials():
    db = database()
    service, job = await prepared(db)
    await service.expire(job, now=NOW + timedelta(minutes=16))
    assert not await service.install(job, "owner", "g", {"session_cookie_enc": "cached-cipher", "jsession_id": "cached-cipher", "status": "active"}, now=NOW + timedelta(minutes=16))
    assert not db.outreach_accounts.docs[0].get("session_cookie_enc")
    assert "li_at_enc" not in db.outreach_connection_jobs.docs[0]
    assert db.outreach_connection_jobs.docs[0]["status"] == "finalizing"
    assert db.outreach_proxy_leases.docs and db.outreach_connection_locks.docs

@pytest.mark.asyncio
async def test_stop_installed_generation_scrubs_secrets_and_retains_connected_ip():
    db = database()
    service, job = await prepared(db)
    assert await service.install(job, "owner", "g", {"session_cookie_enc": "cipher", "jsession_id": "cipher", "status": "active"}, now=NOW)
    view = await service.inspect("w", "j")
    result = await service.resolve("w", "j", "stop_and_scrub", "operator", "Verified the exact installed generation after draining workers.", workers_drained=True, expected_digest=view["review_digest"])
    assert result["status"] == "repaired_stopped"
    assert not db.outreach_accounts.docs[0].get("session_cookie_enc")
    assert db.outreach_accounts.docs[0]["status"] == "reauth_required"
    assert db.outreach_proxy_leases.docs and db.outreach_sender_slots.docs
    assert not db.outreach_connection_locks.docs
    assert db.outreach_sender_execution.docs[0]["permission"]["latched"]

@pytest.mark.asyncio
async def test_proven_uninstalled_connection_releases_only_job_bound_new_resources():
    db = database()
    service, _ = await prepared(db)
    view = await service.inspect("w", "j")
    await service.resolve("w", "j", "stop_and_scrub", "operator", "No installed credentials exist; the original fence is closed.", workers_drained=True, expected_digest=view["review_digest"])
    assert not db.outreach_proxy_leases.docs and not db.outreach_sender_slots.docs
    assert db.outreach_proxy_inventory.docs[0]["status"] == "available"

@pytest.mark.asyncio
async def test_repair_never_touches_a_replacement_account_generation():
    db = database()
    service, job = await prepared(db)
    await service.install(job, "owner", "g", {"session_cookie_enc": "old", "status": "active"}, now=NOW)
    db.outreach_accounts.docs[0].update(credential_generation="new-generation", session_cookie_enc="new-cipher")
    view = await service.inspect("w", "j")
    with pytest.raises(ValueError):
        await service.resolve("w", "j", "stop_and_scrub", "operator", "The current account differs from the original activation.", workers_drained=True, expected_digest=view["review_digest"])
    assert db.outreach_accounts.docs[0]["session_cookie_enc"] == "new-cipher"
    assert db.outreach_proxy_leases.docs and db.outreach_connection_locks.docs


def test_deadline_is_bounded_by_original_capture_not_reaper_start():
    assert credential_deadline({"created_at": NOW}) == NOW + timedelta(minutes=15)
    assert credential_deadline({"custody_started_at": NOW, "finalizing_at": NOW + timedelta(minutes=14)}) == NOW + timedelta(minutes=15)


@pytest.mark.asyncio
async def test_installed_retain_retries_after_account_commit_and_job_outage(monkeypatch):
    db = database()
    db.outreach_entitlements.docs.append({"workspace_id": "w", "status": "active", "seats": 1,
        "payment_source": "manual_verified_invoice", "paid_through": NOW + timedelta(days=1)})
    service, job = await prepared(db)
    assert await service.install(job, "owner", "g", {"session_cookie_enc": "cipher", "status": "active", "proxy": {"proxy_id": "ip"}}, now=NOW)
    view = await service.inspect("w", "j")
    update = db.outreach_connection_jobs.update_one
    async def fail_terminal(query, changes, **kwargs):
        if changes.get("$set", {}).get("status") == "completed":
            raise RuntimeError("fake completion outage")
        return await update(query, changes, **kwargs)
    monkeypatch.setattr(db.outreach_connection_jobs, "update_one", fail_terminal)
    with pytest.raises(RuntimeError):
        await service.resolve("w", "j", "retain_installed", "operator", "Verified the installed session and independent paid/IP terms.", workers_drained=True, expected_digest=view["review_digest"])
    assert db.outreach_accounts.docs[0]["connection_finalization"]["state"] == "closed"
    monkeypatch.setattr(db.outreach_connection_jobs, "update_one", update)
    assert (await service.finish("w", "j"))["status"] == "completed"
    assert db.outreach_accounts.docs[0]["session_cookie_enc"] == "cipher"
    assert db.outreach_proxy_leases.docs and not db.outreach_connection_locks.docs
    assert db.outreach_sender_execution.docs[0]["permission"]["latched"]


@pytest.mark.asyncio
async def test_stop_repair_lock_cleanup_outage_retries_without_releasing_installed_assets(monkeypatch):
    db = database()
    service, job = await prepared(db)
    await service.install(job, "owner", "g", {"session_cookie_enc": "cipher", "status": "active"}, now=NOW)
    view = await service.inspect("w", "j")
    delete = db.outreach_connection_locks.delete_one
    async def unavailable(*args, **kwargs):
        raise RuntimeError("fake lock cleanup outage")
    monkeypatch.setattr(db.outreach_connection_locks, "delete_one", unavailable)
    with pytest.raises(RuntimeError):
        await service.resolve("w", "j", "stop_and_scrub", "operator", "Verified this exact session generation after worker draining.", workers_drained=True, expected_digest=view["review_digest"])
    assert db.outreach_connection_jobs.docs[0]["status"] == "repaired_stopped"
    assert not db.outreach_connection_jobs.docs[0].get("repair_cleanup_complete")
    monkeypatch.setattr(db.outreach_connection_locks, "delete_one", delete)
    await service.sweep()
    assert db.outreach_connection_jobs.docs[0]["repair_cleanup_complete"]
    assert db.outreach_proxy_leases.docs and not db.outreach_connection_locks.docs


@pytest.mark.asyncio
async def test_repair_keeps_resources_reserved_by_another_job():
    db = database()
    service, _ = await prepared(db)
    db.outreach_proxy_leases.docs[0]["reservation_job_id"] = "replacement"
    db.outreach_sender_slots.docs[0]["reservation_job_id"] = "replacement"
    view = await service.inspect("w", "j")
    await service.resolve("w", "j", "stop_and_scrub", "operator", "Verified no install occurred and inspected resource ownership.", workers_drained=True, expected_digest=view["review_digest"])
    assert db.outreach_proxy_leases.docs and db.outreach_sender_slots.docs


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["drain", "digest", "decision", "paid"])
async def test_invalid_or_unpaid_repair_cannot_restore_credentials(fault):
    db = database()
    service, job = await prepared(db)
    await service.install(job, "owner", "g", {"session_cookie_enc": "cipher", "status": "active"}, now=NOW)
    view = await service.inspect("w", "j")
    with pytest.raises(ValueError):
        await service.resolve("w", "j", "retain_installed" if fault == "paid" else "invalid" if fault == "decision" else "stop_and_scrub",
            "operator", "Independently verified this sender and original job custody.", workers_drained=fault != "drain",
            expected_digest="stale" if fault == "digest" else view["review_digest"])
    assert db.outreach_proxy_leases.docs


@pytest.mark.asyncio
async def test_missing_timestamp_legacy_pending_job_is_scrubbed_with_live_actions_off(monkeypatch):
    from celery_workers.tasks import outreach as worker
    db = database()
    job = db.outreach_connection_jobs.docs[0]
    job.pop("created_at")
    job.pop("custody_expires_at")
    job["status"] = "queued"
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "false")
    assert (await worker._clean_stale_connections(db=db))["cleaned"] == 0
    assert "li_at_enc" not in job and "jsession_id_enc" not in job
    assert job["status"] == "finalizing"
    assert db.outreach_proxy_leases.docs and db.outreach_sender_slots.docs


@pytest.mark.asyncio
async def test_finalizing_expiry_scrubs_all_jobs_despite_first_generation_conflict():
    db = database()
    service, job = await prepared(db)
    await service.install(job, "owner", "g", {"session_cookie_enc": "cipher", "status": "active"}, now=NOW)
    db.outreach_accounts.docs[0]["credential_generation"] = "replacement"
    db.outreach_connection_jobs.docs.append({**db.outreach_connection_jobs.docs[0], "id": "other", "sender_id": "other"})
    await service.sweep(now=NOW + timedelta(minutes=16))
    assert all("li_at_enc" not in item for item in db.outreach_connection_jobs.docs)
    assert db.outreach_accounts.docs[0]["credential_generation"] == "replacement"


@pytest.mark.asyncio
async def test_reconnect_preparation_preserves_old_generation_until_install():
    db = database()
    db.outreach_accounts.docs.append({"id": "a", "workspace_id": "w", "credential_generation": "old",
        "linkedin_urn": "urn:sender", "session_cookie_enc": "old-cipher", "status": "reauth_required"})
    db.outreach_connection_jobs.docs[0].update(reconnect=True, base_credential_generation="old")
    service, job = await prepared(db)
    assert db.outreach_accounts.docs[0]["session_cookie_enc"] == "old-cipher"
    assert await service.install(job, "owner", "g", {"session_cookie_enc": "new-cipher", "status": "active"}, now=NOW)
    assert db.outreach_accounts.docs[0]["credential_generation"] == "g"


@pytest.mark.asyncio
async def test_expiry_snapshot_cannot_override_a_saved_operator_repair():
    db = database()
    service, old_job = await prepared(db)
    db.outreach_connection_jobs.docs[0].update(status="repairing", repair={"decision": "retain_installed"})
    await service.expire(old_job, now=NOW + timedelta(minutes=16))
    assert db.outreach_accounts.docs[0]["connection_finalization"]["state"] == "prepared"
    assert db.outreach_connection_jobs.docs[0]["li_at_enc"] == "cipher"


@pytest.mark.asyncio
async def test_prepared_running_crash_blocks_a_new_execution_grant():
    from outreach.core.execution_permission import ExecutionPermission
    db = database()
    job = await db.outreach_connection_jobs.find_one({"id": "j"})
    await ConnectionRepair(db).prepare(job, "owner", "g", {"account_name": "Sender", "linkedin_urn": "urn:sender"}, now=NOW)
    with pytest.raises(ValueError, match="finalization"):
        await ExecutionPermission(db).grant("w", "a", "g", ["sequence"], "operator", clear_latch=True)


@pytest.mark.asyncio
async def test_connection_repair_resolves_only_original_verification_read():
    from outreach.core.sender_execution import SenderExecution
    db = database()
    service, _ = await prepared(db)
    await db.outreach_physical_requests.insert_one({"_id": "read", "workspace_id": "w", "sender_id": "a",
        "source": "verify", "credential_generation": "pending:j", "mutation": False, "owner_token": "reader",
        "status": "unknown_outcome", "action": "read"})
    await db.outreach_sender_execution.insert_one({**SenderExecution.scope("w", "a"), "status": "in_flight",
        "owner_token": "reader", "physical_request_token": "read"})
    view = await service.inspect("w", "j")
    assert view["verification_requests"][0]["_id"] == "read"
    await service.resolve("w", "j", "stop_and_scrub", "operator", "Inspected the interrupted verification after all workers drained.",
        workers_drained=True, expected_digest=view["review_digest"])
    assert db.outreach_physical_requests.docs[0]["resolution"]["decision"] == "read_interrupted"
    assert "physical_request_token" not in db.outreach_sender_execution.docs[0]


@pytest.mark.asyncio
async def test_v2_unused_reservation_cleanup_retries_after_resource_write_outage(monkeypatch):
    from celery_workers.tasks import outreach as worker
    db = database()
    job = db.outreach_connection_jobs.docs[0]
    job.update(installation_protocol=2, status="queued", created_at=NOW - timedelta(minutes=20), custody_expires_at=NOW - timedelta(minutes=5))
    original = db.outreach_proxy_leases.delete_one
    async def unavailable(*args, **kwargs):
        raise RuntimeError("fake proxy cleanup outage")
    monkeypatch.setattr(db.outreach_proxy_leases, "delete_one", unavailable)
    monkeypatch.setattr(worker, "is_shutting_down", lambda: False)
    await worker._clean_stale_connections(db=db)
    assert job["status"] == "failed" and not job["pending_cleanup_complete"]
    assert "created_at" not in job and "li_at_enc" not in job
    monkeypatch.setattr(db.outreach_proxy_leases, "delete_one", original)
    job.pop("next_custody_check_at")
    assert (await worker._clean_stale_connections(db=db))["cleaned"] == 1
    assert job["pending_cleanup_complete"] and not db.outreach_proxy_leases.docs


@pytest.mark.asyncio
async def test_terminal_cleanup_retry_never_scrubs_replacement_generation(monkeypatch):
    db = database()
    service, job = await prepared(db)
    await service.install(job, "owner", "g", {"session_cookie_enc": "cipher", "status": "active"}, now=NOW)
    view = await service.inspect("w", "j")
    original = db.outreach_connection_locks.delete_one
    async def committed_without_ack(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("fake lock acknowledgement loss")
    monkeypatch.setattr(db.outreach_connection_locks, "delete_one", committed_without_ack)
    with pytest.raises(RuntimeError):
        await service.resolve("w", "j", "stop_and_scrub", "operator", "Verified the original installed generation after worker draining.", workers_drained=True, expected_digest=view["review_digest"])
    db.outreach_accounts.docs[0].update(credential_generation="new-generation", session_cookie_enc="new-cipher")
    monkeypatch.setattr(db.outreach_connection_locks, "delete_one", original)
    await service.finish("w", "j")
    assert db.outreach_accounts.docs[0]["session_cookie_enc"] == "new-cipher"


@pytest.mark.asyncio
async def test_unfinished_retain_can_be_explicitly_stopped_with_fresh_review_and_audit(monkeypatch):
    db = database()
    db.outreach_entitlements.docs.append({"workspace_id": "w", "status": "active", "seats": 1,
        "payment_source": "manual_verified_invoice", "paid_through": NOW + timedelta(days=1)})
    service, job = await prepared(db)
    await service.install(job, "owner", "g", {"session_cookie_enc": "cipher", "proxy": {"proxy_id": "ip"}, "status": "active"}, now=NOW)
    view = await service.inspect("w", "j")
    update = db.outreach_connection_jobs.update_one
    async def unavailable(query, changes, **kwargs):
        if changes.get("$set", {}).get("status") == "completed":
            raise RuntimeError("fake completion outage")
        return await update(query, changes, **kwargs)
    monkeypatch.setattr(db.outreach_connection_jobs, "update_one", unavailable)
    with pytest.raises(RuntimeError):
        await service.resolve("w", "j", "retain_installed", "first-operator", "Verified the existing session and paid/IP terms after draining.", workers_drained=True, expected_digest=view["review_digest"])
    monkeypatch.setattr(db.outreach_connection_jobs, "update_one", update)
    new_view = await service.inspect("w", "j")
    await service.resolve("w", "j", "stop_and_scrub", "second-operator", "Re-inspected the failed repair and elected to stop this session.", workers_drained=True, expected_digest=new_view["review_digest"])
    record = db.outreach_connection_jobs.docs[0]
    assert record["status"] == "repaired_stopped" and record["repair_history"][0]["operator"] == "first-operator"
    assert record["repair"]["operator"] == "second-operator"
    assert not db.outreach_accounts.docs[0].get("session_cookie_enc") and db.outreach_proxy_leases.docs


@pytest.mark.asyncio
async def test_retain_rejects_same_generation_with_changed_cipher_or_proxy():
    db = database()
    db.outreach_entitlements.docs.append({"workspace_id": "w", "status": "active", "seats": 1,
        "payment_source": "manual_verified_invoice", "paid_through": NOW + timedelta(days=1)})
    service, job = await prepared(db)
    await service.install(job, "owner", "g", {"session_cookie_enc": "cipher", "proxy": {"proxy_id": "ip"}, "status": "active"}, now=NOW)
    db.outreach_accounts.docs[0]["session_cookie_enc"] = "changed-cipher"
    view = await service.inspect("w", "j")
    with pytest.raises(ValueError, match="fence"):
        await service.resolve("w", "j", "retain_installed", "operator", "The observed session differs from the original installed session.", workers_drained=True, expected_digest=view["review_digest"])
    assert db.outreach_connection_jobs.docs[0]["status"] == "finalizing"


@pytest.mark.asyncio
async def test_pending_verification_permission_cannot_outlive_original_custody():
    from outreach.core.execution_permission import ExecutionPermission
    db = database()
    near_deadline = NOW + timedelta(minutes=14, seconds=50)
    permission = await ExecutionPermission(db).grant("w", "a", "pending:j", ["verify"], "operator", now=near_deadline)
    assert permission["expires_at"] == NOW + timedelta(minutes=15)
    with pytest.raises(ValueError, match="custody"):
        await ExecutionPermission(db).grant("w", "a", "pending:j", ["verify"], "operator", now=NOW + timedelta(minutes=16))


@pytest.mark.asyncio
async def test_missing_pending_job_cannot_receive_verification_permission():
    from outreach.core.execution_permission import ExecutionPermission
    with pytest.raises(ValueError, match="custody"):
        await ExecutionPermission(database()).grant("w", "a", "pending:another", ["verify"], "operator", now=NOW)
