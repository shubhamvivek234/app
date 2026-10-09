"""Real transaction ordering for suppression insertions and identity changes."""
import asyncio
import os
from unittest.mock import AsyncMock

import httpx
import pytest

from outreach.core.request_guard import RequestDenied
from tests.test_outreach_dispatch_authority import ready_db, dispatch

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Disposable replica set is opt-in")]


async def check_recipient(db):
    from outreach.core.email_finder import is_lead_email_available
    from outreach.core.lead_importer import check_compound_suppression
    from outreach.tasks.sequence_executor import _recipient_has_reply
    lead = await db.outreach_leads.find_one({"workspace_id": "w", "id": "l"})
    if (await check_compound_suppression("w", [lead], db)
            or await _recipient_has_reply(db, "w", "a", lead)
            or not await is_lead_email_available(db, "w", lead)):
        return "lead_suppressed"


async def write_stop(db, kind, *, workspace="w"):
    from outreach.core.email_finder import suppress_email
    from outreach.core.suppression import mutate_suppression
    if kind == "dnc_insert":
        from outreach.api.leads import add_do_not_contact, DoNotContactRequest
        return await add_do_not_contact(DoNotContactRequest(email="lead@example.com"),
            current_user={"user_id": workspace, "default_workspace_id": workspace}, db=db)
    if kind == "email_insert":
        return await suppress_email(db, workspace_id=workspace, email="LEAD@example.com", reason="test")
    if kind in {"thread_insert", "thread_update"}:
        from outreach.engine.inbox_sync import InboxSynchronizer
        return await InboxSynchronizer(db, workspace).persist_conversation("a", {
            "lead_urn": "urn:member:existing" if kind == "thread_update" else "urn:member:new",
            "thread_urn": "urn:thread", "lead_profile_url": "https://www.linkedin.com/in/person",
            "messages": [{"sender_type": "lead", "body": "Thanks"}]})
    async def change(current):
        collection, update = {
            "dnc_update": ("outreach_do_not_contact", {"identifiers.email": "lead@example.com", "email": "lead@example.com"}),
            "email_update": ("outreach_email_suppressions", {"email": "lead@example.com"}),
        }[kind]
        return await current[collection].update_one({"workspace_id": workspace, "id": "unrelated"}, {"$set": update})
    return await mutate_suppression(db, workspace, change)


async def prepare(db):
    await db.outreach_leads.update_one({"workspace_id": "w", "id": "l"}, {"$set": {"email": "lead@example.com"}})
    for name, document in (("outreach_do_not_contact", {"email": "other@example.com"}),
            ("outreach_email_suppressions", {"email": "other@example.com"}),
            ("outreach_inbox_threads", {"account_id": "a", "lead_urn": "urn:member:existing", "lead_profile_url": "https://www.linkedin.com/in/other", "has_lead_reply": True})):
        await db[name].insert_one({"workspace_id": "w", "id": "unrelated", **document})


@pytest.mark.parametrize("kind", ["dnc_insert", "dnc_update", "email_insert", "email_update", "thread_insert", "thread_update"])
async def test_stop_committed_after_transaction_snapshot_before_guard_write_blocks_factory(ready_db, monkeypatch, kind):
    from outreach.core.dispatch_authority import AuthorityDatabase
    db, job = ready_db
    await prepare(db)
    seen, release = asyncio.Event(), asyncio.Event()
    original = AuthorityDatabase.fence_suppression
    once = False
    async def pause(self, workspace):
        nonlocal once
        if not once:
            once = True
            await self.database.outreach_accounts.find_one({"workspace_id": workspace, "id": "a"}, session=self.session)
            seen.set()
            await release.wait()
        return await original(self, workspace)
    monkeypatch.setattr(AuthorityDatabase, "fence_suppression", pause)
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    task = asyncio.create_task(dispatch(db, job, factory, extra_validation=check_recipient))
    try:
        await asyncio.wait_for(seen.wait(), 5)
        await asyncio.wait_for(write_stop(db, kind), 5)
        release.set()
        with pytest.raises(RequestDenied, match="lead_suppressed"):
            await asyncio.wait_for(task, 5)
        factory.assert_not_awaited()
        assert (await db.outreach_physical_requests.find_one({}))["status"] == "not_submitted"
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_writer_waits_when_dispatch_already_holds_workspace_guard(ready_db, monkeypatch):
    from outreach.core.dispatch_authority import AuthorityDatabase
    db, job = ready_db
    await prepare(db)
    seen, release = asyncio.Event(), asyncio.Event()
    original = AuthorityDatabase.fence_suppression
    async def pause(self, workspace):
        result = await original(self, workspace)
        seen.set()
        await release.wait()
        return result
    monkeypatch.setattr(AuthorityDatabase, "fence_suppression", pause)
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    send = asyncio.create_task(dispatch(db, job, factory, extra_validation=check_recipient))
    stop = None
    try:
        await asyncio.wait_for(seen.wait(), 5)
        stop = asyncio.create_task(write_stop(db, "email_insert"))
        await asyncio.sleep(.15)
        assert not stop.done()
        assert not await db.outreach_email_suppressions.find_one({"workspace_id": "w", "email": "lead@example.com"})
        release.set()
        await asyncio.wait_for(send, 5)
        await asyncio.wait_for(stop, 5)
        factory.assert_awaited_once()
        assert await db.outreach_email_suppressions.find_one({"workspace_id": "w", "email": "lead@example.com"})
    finally:
        release.set()
        for task in (send, stop):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (send, stop) if task), return_exceptions=True)


async def test_suppression_failure_rolls_back_both_record_and_guard(ready_db):
    from outreach.core.suppression import mutate_suppression
    db, _ = ready_db
    original_guard = await db.outreach_suppression_guards.find_one({"workspace_id": "w"})
    async def fail(current):
        await current.outreach_email_suppressions.insert_one({"workspace_id": "w", "email": "lead@example.com"})
        raise RuntimeError("test-only persistence interruption")
    with pytest.raises(RuntimeError):
        await mutate_suppression(db, "w", fail)
    assert not await db.outreach_email_suppressions.find_one({"workspace_id": "w"})
    assert await db.outreach_suppression_guards.find_one({"workspace_id": "w"}) == original_guard


async def test_other_workspace_suppression_cannot_block_current_recipient(ready_db):
    db, job = ready_db
    await prepare(db)
    await write_stop(db, "dnc_insert", workspace="other")
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    await dispatch(db, job, factory, extra_validation=check_recipient)
    factory.assert_awaited_once()


async def test_nested_writer_uses_same_transaction_and_workspace(ready_db):
    from outreach.core.suppression import mutate_suppression
    from outreach.core.email_finder import suppress_email
    db, _ = ready_db
    async def outer(current):
        await suppress_email(current, workspace_id="w", email="lead@example.com", reason="reply")
        with pytest.raises(ValueError, match="workspace"):
            await suppress_email(current, workspace_id="other", email="other@example.com", reason="reply")
        return "saved"
    assert await mutate_suppression(db, "w", outer) == "saved"
    assert await db.outreach_email_suppressions.find_one({"workspace_id": "w"})
    assert not await db.outreach_email_suppressions.find_one({"workspace_id": "other"})


async def test_linkedin_reply_writer_commits_thread_and_all_enrollment_stops_once(ready_db):
    from outreach.engine.inbox_sync import InboxSynchronizer
    db, _ = ready_db
    synchronizer = InboxSynchronizer(db, "w")
    conversation = {"lead_urn": "urn:li:member:person", "thread_urn": "urn:thread",
        "lead_profile_url": "https://www.linkedin.com/in/person", "messages": [{"sender_type": "lead", "body": "Thanks"}]}
    result = await synchronizer.persist_conversation("a", conversation)
    assert result["new_replies_detected"] == 1
    assert (await db.outreach_leads.find_one({"id": "l", "workspace_id": "w"}))["has_replied"]
    assert (await db.outreach_inbox_threads.find_one({"workspace_id": "w", "account_id": "a"}))["has_lead_reply"]
    assert (await db.outreach_campaigns.find_one({"workspace_id": "w", "id": "c"}))["replies_count"] == 1
    assert (await synchronizer.persist_conversation("a", conversation))["new_replies_detected"] == 0
    assert (await db.outreach_campaigns.find_one({"workspace_id": "w", "id": "c"}))["replies_count"] == 1


async def test_linkedin_failure_does_not_commit_thread_without_lead_stop(ready_db, monkeypatch):
    from outreach.engine.inbox_sync import InboxSynchronizer
    from outreach.core.suppression import SuppressionCollection
    db, _ = ready_db
    original = SuppressionCollection.update_one
    async def fail(self, query, update, **kwargs):
        if self.collection.name == "outreach_leads":
            raise RuntimeError("test-only lead persistence failure")
        return await original(self, query, update, **kwargs)
    monkeypatch.setattr(SuppressionCollection, "update_one", fail)
    with pytest.raises(RuntimeError):
        await InboxSynchronizer(db, "w").persist_conversation("a", {"lead_urn": "urn:member",
            "thread_urn": "urn:thread", "lead_profile_url": "https://www.linkedin.com/in/person",
            "messages": [{"sender_type": "lead", "body": "Thanks"}]})
    assert not await db.outreach_inbox_threads.find_one({"workspace_id": "w"})
    assert not (await db.outreach_leads.find_one({"id": "l", "workspace_id": "w"})).get("has_replied")


async def seed_email_reply(db):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    await db.outreach_email_operations.insert_one({"workspace_id": "w", "sender_account_id": "a", "lead_id": "l",
        "campaign_id": "c", "status": "accepted", "recipient": "lead@example.com", "message_id": "<sent@unravler>",
        "accepted_at": now - timedelta(minutes=1)})
    return {"workspace_id": "w", "sender_account_id": "a", "email": "sender@example.com"}, {
        "id": "inbound", "from": "alias@example.com", "received_at": now, "in_reply_to": "<sent@unravler>"}


async def test_email_reply_commits_original_address_suppression_and_lead_stop_once(ready_db):
    from outreach.core.mailbox_sync import _mark_inbound
    db, _ = ready_db
    mailbox, message = await seed_email_reply(db)
    assert (await _mark_inbound(db, mailbox, message))["status"] == "reply"
    assert await db.outreach_email_suppressions.find_one({"workspace_id": "w", "email": "lead@example.com"})
    assert not await db.outreach_email_suppressions.find_one({"workspace_id": "w", "email": "alias@example.com"})
    assert (await db.outreach_leads.find_one({"id": "l", "workspace_id": "w"}))["has_replied"]
    assert (await db.outreach_campaigns.find_one({"workspace_id": "w", "id": "c"}))["replies_count"] == 1
    assert (await _mark_inbound(db, mailbox, message))["status"] == "duplicate"
    assert (await db.outreach_campaigns.find_one({"workspace_id": "w", "id": "c"}))["replies_count"] == 1


async def test_email_reply_rollback_keeps_event_retryable_and_no_partial_stop(ready_db, monkeypatch):
    from outreach.core.mailbox_sync import _mark_inbound
    from outreach.core.suppression import SuppressionCollection
    db, _ = ready_db
    mailbox, message = await seed_email_reply(db)
    original = SuppressionCollection.update_one
    async def fail(self, query, update, **kwargs):
        if self.collection.name == "outreach_leads":
            raise RuntimeError("test-only inbound persistence interruption")
        return await original(self, query, update, **kwargs)
    monkeypatch.setattr(SuppressionCollection, "update_one", fail)
    with pytest.raises(RuntimeError):
        await _mark_inbound(db, mailbox, message)
    assert not await db.outreach_email_suppressions.find_one({"workspace_id": "w"})
    assert not await db.outreach_email_inbound_events.find_one({"workspace_id": "w"})
    assert not (await db.outreach_leads.find_one({"workspace_id": "w", "id": "l"})).get("has_replied")


async def test_concurrent_first_writers_share_one_stable_guard(ready_db):
    from outreach.core.email_finder import suppress_email
    db, _ = ready_db
    # The permission fixture now creates a guard; remove it to exercise first-writer creation.
    await db.outreach_suppression_guards.delete_one({"workspace_id": "w"})
    assert all(await asyncio.gather(*(suppress_email(db, workspace_id="w", email=f"person{n}@example.com", reason="test") for n in range(12))))
    assert await db.outreach_suppression_guards.count_documents({"workspace_id": "w"}) == 1
    assert (await db.outreach_suppression_guards.find_one({"workspace_id": "w"}))["revision"] == 12
    assert await db.outreach_email_suppressions.count_documents({"workspace_id": "w"}) == 12


async def test_deleted_guard_during_dispatch_is_not_recreated_inside_transaction(ready_db, monkeypatch):
    from outreach.core.dispatch_authority import AuthorityDatabase
    db, job = ready_db
    original = AuthorityDatabase.fence_suppression
    async def remove(self, workspace):
        await db.outreach_suppression_guards.delete_one({"workspace_id": workspace})
        return await original(self, workspace)
    monkeypatch.setattr(AuthorityDatabase, "fence_suppression", remove)
    factory = AsyncMock(return_value=httpx.Response(201, json={}))
    with pytest.raises(RequestDenied):
        await dispatch(db, job, factory)
    factory.assert_not_awaited()


@pytest.mark.parametrize("kind", ["linkedin", "email"])
async def test_existing_indexed_reply_event_is_reused_without_aborting_stop(ready_db, kind):
    from outreach.engine.inbox_sync import InboxSynchronizer
    from outreach.core.mailbox_sync import _mark_inbound
    db, _ = ready_db
    await db.outreach_event_outbox.create_index([("workspace_id", 1), ("dedupe_key", 1)], unique=True)
    dedupe = "lead.replied:linkedin:l" if kind == "linkedin" else "lead.replied:email:l:inbound"
    await db.outreach_event_outbox.insert_one({"workspace_id": "w", "dedupe_key": dedupe, "id": "original-event"})
    if kind == "linkedin":
        await InboxSynchronizer(db, "w").persist_conversation("a", {"lead_urn": "urn:member", "thread_urn": "urn:thread",
            "lead_profile_url": "https://www.linkedin.com/in/person", "messages": [{"sender_type": "lead", "body": "Thanks"}]})
    else:
        mailbox, message = await seed_email_reply(db)
        await _mark_inbound(db, mailbox, message)
    assert (await db.outreach_leads.find_one({"workspace_id": "w", "id": "l"}))["has_replied"]
    assert await db.outreach_event_outbox.count_documents({"workspace_id": "w", "dedupe_key": dedupe}) == 1
    assert (await db.outreach_event_outbox.find_one({"workspace_id": "w", "dedupe_key": dedupe}))["id"] == "original-event"


async def test_outbox_transaction_error_is_retried_with_no_partial_counts(ready_db, monkeypatch):
    from outreach.engine.inbox_sync import InboxSynchronizer
    from outreach.core.suppression import SuppressionCollection
    from pymongo.errors import OperationFailure
    db, _ = ready_db
    original = SuppressionCollection.update_one
    calls = 0
    async def transient(self, query, update, **kwargs):
        nonlocal calls
        if self.collection.name == "outreach_event_outbox":
            calls += 1
            if calls == 1:
                raise OperationFailure("test-only transaction retry", code=112,
                    details={"errorLabels": ["TransientTransactionError"]})
        return await original(self, query, update, **kwargs)
    monkeypatch.setattr(SuppressionCollection, "update_one", transient)
    result = await InboxSynchronizer(db, "w").persist_conversation("a", {"lead_urn": "urn:member", "thread_urn": "urn:thread",
        "lead_profile_url": "https://www.linkedin.com/in/person", "messages": [{"sender_type": "lead", "body": "Thanks"}]})
    assert calls == 2
    assert result["new_replies_detected"] == 1
    assert await db.outreach_inbox_threads.count_documents({"workspace_id": "w"}) == 1
    assert (await db.outreach_campaigns.find_one({"workspace_id": "w", "id": "c"}))["replies_count"] == 1


@pytest.mark.parametrize("target", ["original@example.com", "discovered@example.com"])
async def test_dnc_matches_both_saved_identifiers_and_current_email(ready_db, target):
    from outreach.core.lead_importer import check_compound_suppression
    from outreach.api.leads import add_do_not_contact, DoNotContactRequest
    db, _ = ready_db
    await add_do_not_contact(DoNotContactRequest(email=target), current_user={"user_id": "w"}, db=db)
    candidate = {"identifiers": {"email": "original@example.com"}, "email": "discovered@example.com"}
    assert 0 in await check_compound_suppression("w", [candidate], db)


async def test_adding_dnc_by_one_alias_does_not_remove_previous_aliases(ready_db):
    from outreach.core.lead_importer import check_compound_suppression
    from outreach.api.leads import add_do_not_contact, DoNotContactRequest
    db, _ = ready_db
    await add_do_not_contact(DoNotContactRequest(email="lead@example.com", linkedin_url="https://linkedin.com/in/person"),
        current_user={"user_id": "w"}, db=db)
    await add_do_not_contact(DoNotContactRequest(email="lead@example.com"), current_user={"user_id": "w"}, db=db)
    assert 0 in await check_compound_suppression("w", [{"linkedin_url": "https://www.linkedin.com/in/person"}], db)


@pytest.mark.parametrize("retry", [False, True])
async def test_stale_fetched_conversation_preserves_newer_reply_content_and_timestamp(ready_db, monkeypatch, retry):
    from datetime import datetime, timedelta, timezone
    from pymongo.errors import OperationFailure
    from outreach.engine.inbox_sync import InboxSynchronizer
    from outreach.core import suppression
    db, _ = ready_db
    now = datetime.now(timezone.utc)
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)
    newer = {"lead_urn": "urn:member", "thread_urn": "urn:thread", "lead_profile_url": "https://www.linkedin.com/in/person",
        "last_message_at": now, "last_message_snippet": "Latest reply", "messages": [{"sender_type": "lead", "body": "Latest reply", "timestamp": now}]}
    older = {**newer, "last_message_at": now - timedelta(minutes=5), "last_message_snippet": "Old outbound",
        "messages": [{"sender_type": "user", "body": "Old outbound", "timestamp": now - timedelta(minutes=5)}]}
    synchronizer = InboxSynchronizer(db, "w")
    if retry:
        original_touch = suppression.touch_suppression_guard
        calls = 0
        async def interrupt(current, workspace, session):
            nonlocal calls
            calls += 1
            if calls == 1:
                await original_touch(current, workspace, session)
                raise OperationFailure("test-only retry", code=112, details={"errorLabels": ["TransientTransactionError"]})
            if calls == 2:
                await synchronizer.persist_conversation("a", newer)
            return await original_touch(current, workspace, session)
        monkeypatch.setattr(suppression, "touch_suppression_guard", interrupt)
    else:
        await synchronizer.persist_conversation("a", newer)
    await synchronizer.persist_conversation("a", older)
    saved = await db.outreach_inbox_threads.find_one({"workspace_id": "w", "lead_urn": "urn:member"})
    assert saved["has_lead_reply"]
    assert saved["last_message_at"] == now
    assert saved["last_message_snippet"] == "Latest reply"
    assert any(message["body"] == "Latest reply" for message in saved["messages"])


@pytest.mark.parametrize("age_minutes", [0, 5, None])
async def test_late_reply_enrichment_is_preserved_without_regressing_newer_content(ready_db, age_minutes):
    from datetime import datetime, timedelta, timezone
    from outreach.engine.inbox_sync import InboxSynchronizer
    db, _ = ready_db
    now = datetime.now(timezone.utc)
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)
    base = {"lead_urn": "urn:member", "thread_urn": "urn:thread", "lead_profile_url": "https://www.linkedin.com/in/person",
        "last_message_at": now, "last_message_snippet": "Latest outbound",
        "messages": [{"sender_type": "user", "body": "Latest outbound", "timestamp": now}]}
    synchronizer = InboxSynchronizer(db, "w")
    await synchronizer.persist_conversation("a", base)
    enrichment = {**base, "last_message_at": now - timedelta(minutes=age_minutes or 0), "last_message_snippet": "Observed reply",
        "messages": [{"sender_type": "lead", "body": "Observed reply", "timestamp": now - timedelta(minutes=age_minutes or 0)}]}
    if age_minutes is None:
        enrichment.pop("last_message_at")
        enrichment["messages"][0].pop("timestamp")
    await synchronizer.persist_conversation("a", enrichment)
    await synchronizer.persist_conversation("a", enrichment)
    saved = await db.outreach_inbox_threads.find_one({"workspace_id": "w", "lead_urn": "urn:member"})
    assert saved["has_lead_reply"]
    assert saved["last_message_at"] == now and saved["last_message_snippet"] == "Latest outbound"
    assert sorted(message["body"] for message in saved["messages"]) == ["Latest outbound", "Observed reply"]


@pytest.mark.parametrize("stored_host,new_host", [("linkedin.com", "www.linkedin.com"), ("www.linkedin.com", "linkedin.com")])
async def test_later_enrollment_with_other_url_host_stops_in_actual_sequence_preflight(ready_db, stored_host, new_host):
    from datetime import datetime, timezone
    from outreach.engine.inbox_sync import InboxSynchronizer
    from outreach.core.authorization import authorization_snapshot
    from outreach.tasks.sequence_executor import _preflight_dispatch
    db, _ = ready_db
    original = await db.outreach_leads.find_one({"workspace_id": "w", "id": "l"})
    await InboxSynchronizer(db, "w").persist_conversation("a", {"lead_urn": "urn:member", "thread_urn": "urn:thread",
        "lead_profile_url": f"https://{stored_host}/in/person", "messages": [{"sender_type": "lead", "body": "Thanks"}]})
    new = {key: value for key, value in original.items() if key != "_id"}
    new.update({"id": "later", "linkedin_url": f"https://{new_host}/in/person", "has_replied": False})
    await db.outreach_leads.insert_one(new)
    now = datetime.now(timezone.utc)
    await db.outreach_accounts.update_one({"workspace_id": "w", "id": "a"}, {"$set": {"inbox_sync": {
        "status": "complete", "credential_generation": "g", "parser_version": 1,
        "coverage_started_at": now, "completed_at": now}}})
    await db.outreach_campaigns.update_one({"workspace_id": "w", "id": "c"}, {"$set": {"schedule": {
        "timezone": "UTC", "days": list(range(7)), "start_time": "00:00", "end_time": "23:59"}}})
    account = await db.outreach_accounts.find_one({"workspace_id": "w", "id": "a"})
    campaign = await db.outreach_campaigns.find_one({"workspace_id": "w", "id": "c"})
    sequence = await db.outreach_sequences.find_one({"workspace_id": "w", "campaign_id": "c"})
    assert await _preflight_dispatch(db, new, authorization_snapshot(campaign, account, sequence), "send_message") == "lead_suppressed"


@pytest.mark.parametrize("source_time", ["numeric", "missing"])
async def test_message_timestamp_formats_keep_enrichment_idempotent(ready_db, source_time):
    from datetime import datetime, timedelta, timezone
    from outreach.engine.inbox_sync import InboxSynchronizer
    db, _ = ready_db
    now = datetime.now(timezone.utc)
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)
    base = {"lead_urn": "urn:member", "thread_urn": "urn:thread", "lead_profile_url": "https://www.linkedin.com/in/person",
        "last_message_at": now, "messages": [{"sender_type": "user", "body": "Outbound", "timestamp": now}]}
    synchronizer = InboxSynchronizer(db, "w")
    await synchronizer.persist_conversation("a", base)
    reply = {"sender_type": "lead", "body": "Reply"}
    if source_time == "numeric":
        reply["timestamp"] = (now - timedelta(minutes=1)).timestamp()
    enriched = {**base, "messages": [reply]}
    await synchronizer.persist_conversation("a", enriched)
    await synchronizer.persist_conversation("a", enriched)
    saved = await db.outreach_inbox_threads.find_one({"workspace_id": "w", "lead_urn": "urn:member"})
    assert saved["has_lead_reply"]
    assert sorted(message["body"] for message in saved["messages"]) == ["Outbound", "Reply"]


@pytest.mark.parametrize("epoch_scale", [1, 1000])
async def test_numeric_conversation_timestamp_is_normalized_on_insert_and_repeat(ready_db, epoch_scale):
    from datetime import datetime, timezone
    from outreach.engine.inbox_sync import InboxSynchronizer
    db, _ = ready_db
    now = datetime.now(timezone.utc)
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)
    conversation = {"lead_urn": "urn:member", "thread_urn": "urn:thread",
        "last_message_at": now.timestamp() * epoch_scale, "last_message_snippet": "Reply",
        "messages": [{"sender_type": "lead", "body": "Reply"}]}
    synchronizer = InboxSynchronizer(db, "w")
    await synchronizer.persist_conversation("a", conversation)
    await synchronizer.persist_conversation("a", conversation)
    saved = await db.outreach_inbox_threads.find_one({"workspace_id": "w", "lead_urn": "urn:member"})
    assert saved["last_message_at"] == now
    assert saved["has_lead_reply"]
    assert [message["body"] for message in saved["messages"]] == ["Reply"]
