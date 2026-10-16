"""Actual Mongo organization transactions, access races, sync and erasure."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import os

from bson import ObjectId
from fastapi import HTTPException
import pytest

from outreach.api import inbox
from outreach.core import inbox_organization as org
from outreach.core.suppression import SuppressionCollection, guard_scope
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_authorized_context import app_for, client_for

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Owned native Mongo opt-in")]
USER = {"user_id": "actor", "firebase_uid": "uid", "default_workspace_id": "w", "workspace_ids": ["w"]}


async def seed(db):
    await db.users.insert_one({"user_id": "actor", "firebase_uid": "uid", "status": "active"})
    await db.workspaces.insert_one({"workspace_id": "w", "owner_id": "actor"})
    await db.workspace_members.insert_one({"workspace_id": "w", "user_id": "actor", "role": "editor"})
    row = {"id": "t", "workspace_id": "w", "account_id": "sender", "lead_urn": "urn:member:person",
        "conversation_urn": "urn:thread:person", "lead_name": "Person", "thread_revision": 3,
        "unread_count": 2, "has_lead_reply": True, "messages": [{"id": "original", "sender_type": "lead", "body": "Thanks"}],
        "last_message_at": datetime.now(timezone.utc)}
    await db.outreach_inbox_threads.insert_one(row)
    return await db.outreach_inbox_threads.find_one({"_id": row["_id"]})


async def edit(db, changes, row=None):
    row = row or await db.outreach_inbox_threads.find_one({"id": "t", "workspace_id": "w"})
    context = org.public_organization(row)
    return await org.update_organization(db, "w", "actor", "t", context["revision"], context["review_digest"], changes, authenticated_uid="uid")


async def test_star_note_archive_and_restore_preserve_all_execution_and_reply_fields(replica_db):
    before = await seed(replica_db)
    for changes in ({"is_starred": True}, {"note": "<b>Plain text</b>\nCall tomorrow"}, {"is_archived": True}, {"is_archived": False}, {"note": ""}):
        await edit(replica_db, changes)
    saved = await replica_db.outreach_inbox_threads.find_one({"id": "t"})
    assert {key: value for key, value in saved.items() if key != "inbox_organization"} == before
    assert saved["inbox_organization"]["revision"] == 5 and saved["inbox_organization"]["is_starred"]
    assert saved["inbox_organization"]["note"] == ""
    assert not await replica_db.outreach_tasks.count_documents({})
    assert not await replica_db.outreach_intents.count_documents({})
    assert not await replica_db.outreach_sender_execution.count_documents({})


async def test_concurrent_same_revision_has_one_winner_and_no_lost_update(replica_db):
    row = await seed(replica_db)
    results = await asyncio.gather(edit(replica_db, {"note": "one"}, row), edit(replica_db, {"is_starred": True}, row), return_exceptions=True)
    assert sum(isinstance(value, dict) for value in results) == 1
    assert sum(isinstance(value, HTTPException) and value.status_code == 409 for value in results) == 1
    assert (await replica_db.outreach_inbox_threads.find_one({}))["inbox_organization"]["revision"] == 1


@pytest.mark.parametrize("change", ["native", "sender", "conversation", "lead", "duplicate", "workspace_array", "id_array"])
async def test_replaced_or_ambiguous_context_never_receives_older_edit(replica_db, change):
    row = await seed(replica_db)
    if change == "native":
        await replica_db.outreach_inbox_threads.delete_one({"_id": row["_id"]})
        await replica_db.outreach_inbox_threads.insert_one({**row, "_id": ObjectId()})
    elif change == "duplicate":
        await replica_db.outreach_inbox_threads.insert_one({**row, "_id": ObjectId()})
    else:
        field, value = {"sender": ("account_id", "other"), "conversation": ("conversation_urn", "other"),
            "lead": ("lead_urn", "other"), "workspace_array": ("workspace_id", ["w", "foreign"]),
            "id_array": ("id", ["t", "other"])}[change]
        await replica_db.outreach_inbox_threads.update_one({"_id": row["_id"]}, {"$set": {field: value}})
    before = await replica_db.outreach_inbox_threads.find({}).to_list(10)
    with pytest.raises(HTTPException) as failure:
        await edit(replica_db, {"note": "must not appear"}, row)
    assert failure.value.status_code in {404, 409}
    assert await replica_db.outreach_inbox_threads.find({}).to_list(10) == before


@pytest.mark.parametrize("change", ["viewer", "removed", "deleted_user", "identity_erased", "closed", "duplicate_member", "bad_role"])
async def test_current_access_or_erasure_stop_denies_without_metadata(replica_db, change):
    row = await seed(replica_db)
    if change in {"viewer", "bad_role"}:
        await replica_db.workspace_members.update_one({}, {"$set": {"role": "viewer" if change == "viewer" else []}})
    elif change == "removed":
        await replica_db.workspace_members.delete_many({})
        await replica_db.workspaces.update_one({}, {"$set": {"owner_id": "other"}})
    elif change == "duplicate_member":
        await replica_db.workspace_members.insert_one({"workspace_id": "w", "user_id": "actor", "role": "editor"})
    elif change == "deleted_user":
        await replica_db.users.update_one({}, {"$set": {"status": "deletion_pending"}})
    elif change == "identity_erased":
        from outreach.core.erasure import stop_identity
        await stop_identity(replica_db, "uid")
    else:
        await replica_db.outreach_suppression_guards.insert_one({**guard_scope("w"), "erasure_state": "stopped"})
    with pytest.raises(HTTPException) as failure:
        await edit(replica_db, {"is_starred": True}, row)
    assert failure.value.status_code in {403, 503}
    assert await replica_db.outreach_inbox_threads.find_one({"_id": row["_id"]}) == row


async def test_owner_without_membership_can_organize(replica_db):
    await seed(replica_db)
    await replica_db.workspace_members.delete_many({})
    assert (await edit(replica_db, {"note": "owner note"}))["organization"]["note"] == "owner note"


async def test_admitted_uid_cannot_edit_under_replaced_auth_identity(replica_db):
    row = await seed(replica_db)
    await replica_db.users.update_one({}, {"$set": {"firebase_uid": "replacement-uid"}})
    with pytest.raises(HTTPException) as failure: await edit(replica_db, {"note": "old token"}, row)
    assert failure.value.status_code == 403
    assert await replica_db.outreach_inbox_threads.find_one({"_id": row["_id"]}) == row


@pytest.mark.parametrize("uid", [None, "", [], {}, False, "   "])
async def test_missing_or_malformed_captured_auth_identity_denies(replica_db, uid):
    row = await seed(replica_db)
    await replica_db.users.update_one({}, {"$unset": {"firebase_uid": ""}})
    context = org.public_organization(row)
    with pytest.raises(HTTPException) as failure:
        await org.update_organization(replica_db, "w", "actor", "t", 0, context["review_digest"],
            {"note": "blocked"}, authenticated_uid=uid)
    assert failure.value.status_code == 403
    assert await replica_db.outreach_inbox_threads.find_one({"_id": row["_id"]}) == row


async def test_large_bson_integer_revision_roundtrips_and_edits(replica_db):
    await seed(replica_db)
    await replica_db.outreach_inbox_threads.update_one({}, {"$set": {"inbox_organization": {
        "revision": 2**31, "is_starred": False, "is_archived": False, "note": ""}}})
    assert (await edit(replica_db, {"note": "next version"}))["organization"]["revision"] == 2**31 + 1


@pytest.mark.parametrize("malformed", [[], [{"is_archived": True}],
    {"revision": True, "is_archived": True, "is_starred": True, "note": ""},
    {"revision": 1, "is_archived": True, "is_starred": True, "note": []},
    {"revision": 1, "is_archived": [True], "is_starred": True, "note": ""}])
async def test_malformed_metadata_stays_visible_in_inbox_for_review(replica_db, malformed):
    await seed(replica_db)
    await replica_db.outreach_inbox_threads.update_one({}, {"$set": {"inbox_organization": malformed}})
    for view in ("inbox", "all"):
        rows = await inbox.list_inbox_threads(view=view, current_user=USER, db=replica_db)
        assert len(rows) == 1 and not rows[0]["organization"]["editable"]
        assert not rows[0]["organization"]["is_archived"] and not rows[0]["organization"]["is_starred"]
    for view in ("starred", "archived"):
        assert await inbox.list_inbox_threads(view=view, current_user=USER, db=replica_db) == []


async def test_filtered_view_overflow_reports_no_partial_page(replica_db):
    row = await seed(replica_db)
    await replica_db.outreach_inbox_threads.insert_many([{**row, "_id": ObjectId(), "id": f"t-{index}"} for index in range(1000)])
    with pytest.raises(HTTPException) as failure:
        await inbox.list_inbox_threads(view="inbox", current_user=USER, db=replica_db)
    assert failure.value.status_code == 422


@pytest.mark.parametrize("change", ["organization", "sender", "search", "source", "malformed_context"])
async def test_view_change_between_metadata_scan_and_body_read_rejects_page(replica_db, monkeypatch, change):
    await seed(replica_db)
    await replica_db.outreach_inbox_threads.update_one({}, {"$set": {"is_outreach": True}})
    if change == "malformed_context":
        await replica_db.outreach_inbox_threads.update_one({}, {"$set": {"inbox_organization": []}})
    collection = type(replica_db.outreach_inbox_threads)
    original = collection.find
    changed = False
    def interleave(self, query=None, *args, **kwargs):
        nonlocal changed
        cursor = original(self, query, *args, **kwargs)
        if self.name == "outreach_inbox_threads" and isinstance(query, dict) and "_id" in query and not changed:
            changed = True
            class ChangedCursor:
                async def to_list(inner, length):
                    values = {"organization": {"inbox_organization": {"revision": 1, "is_starred": False, "is_archived": True, "note": ""}},
                        "sender": {"account_id": "replacement"}, "search": {"lead_name": "changed"},
                        "source": {"is_outreach": False}, "malformed_context": {"lead_urn": "replacement"}}[change]
                    await replica_db.outreach_inbox_threads.update_one({}, {"$set": values})
                    return await cursor.to_list(length)
            return ChangedCursor()
        return cursor
    monkeypatch.setattr(collection, "find", interleave)
    with pytest.raises(HTTPException) as failure:
        await inbox.list_inbox_threads(view="inbox", account_id="sender", search="Person", source="outreach", current_user=USER, db=replica_db)
    assert changed and failure.value.status_code == 409


async def test_role_change_after_snapshot_retries_and_denies(replica_db, monkeypatch):
    row = await seed(replica_db)
    original = org._authorize
    changed = False
    async def interleave(current, actor, authenticated_uid):
        nonlocal changed
        # Establish a transaction snapshot before the independent role update.
        await current.database.workspace_members.find_one({"workspace_id": "w", "user_id": actor}, session=current.session)
        if not changed:
            changed = True
            await replica_db.workspace_members.update_one({}, {"$set": {"role": "viewer"}})
        return await original(current, actor, authenticated_uid)
    monkeypatch.setattr(org, "_authorize", interleave)
    with pytest.raises(HTTPException) as failure: await edit(replica_db, {"note": "blocked"}, row)
    assert changed and failure.value.status_code == 403
    assert await replica_db.outreach_inbox_threads.find_one({"_id": row["_id"]}) == row


async def test_last_cas_failure_rolls_back_authority_and_metadata(replica_db, monkeypatch):
    await seed(replica_db)
    user = await replica_db.users.find_one({})
    original = SuppressionCollection.update_one
    async def fail(self, query, update, **kwargs):
        if self.collection.name == "outreach_inbox_threads":
            from pymongo.results import UpdateResult
            return UpdateResult({"n": 0, "nModified": 0}, True)
        return await original(self, query, update, **kwargs)
    monkeypatch.setattr(SuppressionCollection, "update_one", fail)
    with pytest.raises(HTTPException) as failure: await edit(replica_db, {"is_archived": True})
    assert failure.value.status_code == 409
    assert await replica_db.users.find_one({}) == user
    assert "inbox_organization" not in await replica_db.outreach_inbox_threads.find_one({})


async def test_lost_acknowledgement_reload_observes_saved_version_without_second_edit(replica_db, monkeypatch):
    from outreach.core.suppression import SuppressionUnavailable
    row = await seed(replica_db)
    original = org.mutate_suppression
    async def commit_then_lose(*args):
        await original(*args)
        raise SuppressionUnavailable("synthetic acknowledgement loss")
    monkeypatch.setattr(org, "mutate_suppression", commit_then_lose)
    with pytest.raises(HTTPException) as failure: await edit(replica_db, {"note": "saved once"}, row)
    assert failure.value.status_code == 503
    monkeypatch.setattr(org, "mutate_suppression", original)
    with pytest.raises(HTTPException) as failure: await edit(replica_db, {"note": "saved once"}, row)
    assert failure.value.status_code == 409
    full = await inbox.get_thread("t", current_user=USER, db=replica_db)
    assert full["organization"]["revision"] == 1 and full["organization"]["note"] == "saved once"
    assert "_id" not in full and "inbox_organization" not in full


async def test_views_combine_with_sender_source_search_and_exclude_foreign_scopes(replica_db):
    row = await seed(replica_db)
    await edit(replica_db, {"is_starred": True})
    for identifier, metadata, workspace in [("archived", {"revision": 1, "is_starred": True, "is_archived": True, "note": "archive"}, "w"),
            ("plain", None, "w"), ("foreign", None, "foreign"), ("array", None, ["w", "foreign"])]:
        copied = {**row, "_id": ObjectId(), "id": identifier, "workspace_id": workspace}
        if metadata: copied["inbox_organization"] = metadata
        await replica_db.outreach_inbox_threads.insert_one(copied)
    expected = {"all": {"t", "archived", "plain"}, "inbox": {"t", "plain"}, "starred": {"t"}, "archived": {"archived"}}
    for view, ids in expected.items():
        result = await inbox.list_inbox_threads(view=view, account_id="sender", search="Person", current_user=USER, db=replica_db)
        assert {value["id"] for value in result} == ids
    assert await inbox.list_inbox_threads(view="all", account_id="other", current_user=USER, db=replica_db) == []


async def test_archived_reply_remains_suppression_authority_and_sync_preserves_notes(replica_db):
    from outreach.tasks.sequence_executor import _recipient_has_reply
    from outreach.engine.inbox_sync import InboxSynchronizer
    await seed(replica_db)
    await edit(replica_db, {"is_archived": True, "is_starred": True, "note": "keep"})
    metadata = (await replica_db.outreach_inbox_threads.find_one({}))["inbox_organization"]
    assert await _recipient_has_reply(replica_db, "w", "sender", {"linkedin_urn": "urn:member:person"})
    await InboxSynchronizer(replica_db, "w").persist_conversation("sender", {"lead_urn": "urn:member:person",
        "thread_urn": "urn:thread:person", "messages": [{"sender_type": "lead", "body": "Another reply"}]})
    saved = await replica_db.outreach_inbox_threads.find_one({"id": "t"})
    assert saved["inbox_organization"] == metadata and saved["has_lead_reply"]
    assert saved["thread_revision"] == 4
    assert await _recipient_has_reply(replica_db, "w", "sender", {"linkedin_urn": "urn:member:person"})


async def test_actual_workspace_erasure_purges_note_without_archived_bypass(replica_db):
    from outreach.core.erasure import OutreachErasure
    await seed(replica_db)
    await edit(replica_db, {"is_archived": True, "note": "private erasure note"})
    service = OutreachErasure(replica_db)
    await service.request("w", "actor")
    inspection = await service.inspect("w")
    result = await service.finish("w", "operator", "All local test workspace writers and caches are drained.",
        workers_drained=True, expected_digest=inspection["review_digest"])
    assert result["status"] == "erased"
    assert not await replica_db.outreach_inbox_threads.count_documents({})
    assert "private erasure note" not in str(await replica_db.outreach_erasure_holds.find({}).to_list(100))


async def test_standalone_denies_without_metadata_fallback(real_db):
    await seed(real_db)
    with pytest.raises(HTTPException) as failure: await edit(real_db, {"is_starred": True})
    assert failure.value.status_code == 503
    assert "inbox_organization" not in await real_db.outreach_inbox_threads.find_one({"workspace_id": "w"})


@pytest.mark.parametrize("role,expected", [("editor", 200), ("viewer", 403)])
async def test_http_permissions_and_strict_payload(replica_db, role, expected):
    row = await seed(replica_db)
    await replica_db.workspace_members.update_one({}, {"$set": {"role": role}})
    context = org.public_organization(row)
    async with client_for(app_for(replica_db, inbox.router, lambda: deepcopy(USER))) as client:
        response = await client.patch("/inbox/t/organization", json={"revision": 0, "review_digest": context["review_digest"], "is_starred": True})
        assert response.status_code == expected
        if role == "editor":
            invalid = await client.patch("/inbox/t/organization", json={"revision": True, "review_digest": context["review_digest"], "is_starred": "false"})
            assert invalid.status_code == 422
            assert (await client.get("/inbox?view=typo")).status_code == 422
