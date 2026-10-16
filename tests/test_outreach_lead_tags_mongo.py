"""Actual transactions, indexes, CSV/Inbox joins and inactive selection drafts."""
import asyncio
from copy import deepcopy
import csv
import io
import os

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
import pytest

from db.indexes import ensure_lead_tag_indexes
from outreach.api import leads, inbox
from outreach.core import lead_tags as tags
from outreach.core.lead_selection import selection_preview, create_selection_draft
from outreach.core.suppression import SuppressionCollection, guard_scope
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_lead_tags import USER, TAG, OTHER_TAG, tag_doc

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Owned local Mongo is opt-in")]


async def seed(db, count=2):
    await ensure_lead_tag_indexes(db)
    await db.outreach_lead_tags.insert_one(tag_doc())
    await db.outreach_leads.insert_many([{"id": f"lead-{index}", "workspace_id": "w", "first_name": f"Alex {index}",
        "linkedin_url": f"https://linkedin.com/in/alex-{index}", "pipeline_stage": "unassigned"} for index in range(count)])


async def test_native_indexes_and_unicode_duplicate_race(replica_db):
    await ensure_lead_tag_indexes(replica_db)
    results = await asyncio.gather(tags.create_tag(replica_db, "w", "actor", "Hot LEAD", "#ff0000"),
        tags.create_tag(replica_db, "w", "actor", "  hot   lead ", "#00ff00"), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
    doc = await replica_db.outreach_lead_tags.find_one({})
    with pytest.raises(DuplicateKeyError): await replica_db.outreach_lead_tags.insert_one({**doc, "_id": "other", "id": OTHER_TAG})
    assert len(await replica_db.outreach_lead_tags.index_information()) == 3


async def test_native_single_revision_race_has_one_winner(replica_db):
    await seed(replica_db)
    results = await asyncio.gather(tags.assign_tags(replica_db, "w", ["lead-0"], TAG, "add", 0),
        tags.assign_tags(replica_db, "w", ["lead-0"], TAG, "add", 0), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert (await replica_db.outreach_leads.find_one({"id": "lead-0"}))["tag_revision"] == 1


async def test_native_bulk_rolls_back_after_late_failure(replica_db, monkeypatch):
    await seed(replica_db)
    original = SuppressionCollection.update_one

    async def fail_second(self, query, update, **kwargs):
        if self.collection.name == "outreach_leads" and query.get("id") == "lead-1":
            raise RuntimeError("synthetic late failure")
        return await original(self, query, update, **kwargs)

    monkeypatch.setattr(SuppressionCollection, "update_one", fail_second)
    with pytest.raises(RuntimeError): await tags.assign_tags(replica_db, "w", ["lead-0", "lead-1"], TAG, "add")
    assert await replica_db.outreach_leads.count_documents({"tag_ids": {"$exists": True}}) == 0


@pytest.mark.parametrize("scope", ["foreign", ["w", "foreign"], None])
async def test_native_foreign_and_array_workspace_never_mutated(replica_db, scope):
    await seed(replica_db)
    await replica_db.outreach_leads.insert_one({"id": "foreign", "workspace_id": scope})
    before = await replica_db.outreach_leads.find({}).to_list(10)
    with pytest.raises(HTTPException) as failure: await tags.assign_tags(replica_db, "w", ["lead-0", "foreign"], TAG, "add")
    assert failure.value.status_code == 404 and await replica_db.outreach_leads.find({}).to_list(10) == before
    await replica_db.outreach_lead_tags.update_one({"id": TAG}, {"$set": {"workspace_id": scope}})
    assert await tags.active_tag_map(replica_db, "w") == {}


async def test_native_closed_workspace_denies_metadata_mutation(replica_db):
    await seed(replica_db)
    await replica_db.outreach_suppression_guards.insert_one({**guard_scope("w"), "erasure_state": "stopped"})
    with pytest.raises(HTTPException) as failure: await tags.assign_tags(replica_db, "w", ["lead-0"], TAG, "add")
    assert failure.value.status_code == 503
    assert await replica_db.outreach_leads.count_documents({"tag_ids": {"$exists": True}}) == 0


async def test_native_filters_export_rename_and_archived_untagged_agree(replica_db):
    await seed(replica_db)
    await tags.assign_tags(replica_db, "w", ["lead-0"], TAG, "add")
    result = await leads.list_leads(tag_ids=TAG, skip=0, limit=50, current_user=USER, db=replica_db)
    assert [lead["id"] for lead in result["leads"]] == ["lead-0"]
    await tags.edit_tag(replica_db, "w", TAG, 1, "=Qualified", "#123456")
    response = await leads.export_leads(tag_ids=TAG, current_user=USER, db=replica_db)
    content = "".join([chunk async for chunk in response.body_iterator])
    exported = list(csv.DictReader(io.StringIO(content)))
    assert len(exported) == 1 and exported[0]["tags"] == "'=Qualified"
    untagged = await leads.list_leads(untagged=True, skip=0, limit=50, current_user=USER, db=replica_db)
    assert [lead["id"] for lead in untagged["leads"]] == ["lead-1"]
    await tags.edit_tag(replica_db, "w", TAG, 2, archive=True)
    untagged = await leads.list_leads(untagged=True, skip=0, limit=50, current_user=USER, db=replica_db)
    assert untagged["total"] == 2
    assert (await replica_db.outreach_leads.find_one({"id": "lead-0"}))["tag_ids"] == [TAG]


async def test_native_inbox_filter_uses_linked_lead_not_legacy_name(replica_db):
    await seed(replica_db)
    await tags.assign_tags(replica_db, "w", ["lead-0"], TAG, "add")
    await replica_db.outreach_inbox_threads.insert_many([
        {"id": "t0", "workspace_id": "w", "lead_id": "lead-0", "tags": ["Old"]},
        {"id": "t1", "workspace_id": "w", "lead_id": "lead-1", "tags": ["Hot lead"]}])
    result = await inbox.list_inbox_threads(tag_ids=TAG, current_user=USER, db=replica_db)
    assert [row["id"] for row in result] == ["t0"] and result[0]["tags"][0]["id"] == TAG
    assert result[0]["legacy_tags"] == ["Old"]


async def test_native_legacy_import_is_explicit_idempotent_and_preserves_unlinked(replica_db):
    await seed(replica_db)
    await replica_db.outreach_inbox_tags.insert_one({"workspace_id": "w", "name": "Qualified", "color": "#abcdef"})
    await replica_db.outreach_inbox_threads.insert_many([
        {"id": "t0", "workspace_id": "w", "lead_id": "lead-0", "tags": ["Hot lead", "Qualified"]},
        {"id": "t1", "workspace_id": "w", "tags": ["Unlinked"]}])
    before = await replica_db.outreach_inbox_threads.find({}).to_list(10)
    await inbox.list_inbox_threads(current_user=USER, db=replica_db)
    assert await replica_db.outreach_inbox_threads.find({}).to_list(10) == before
    result = await tags.migrate_legacy_tags(replica_db, "w", "actor")
    assert result["migrated_threads"] == 1 and len(result["skipped"]) == 1
    thread = await replica_db.outreach_inbox_threads.find_one({"id": "t0"})
    assert "tags" not in thread and thread["legacy_tag_migration"]["original_names"] == ["Hot lead", "Qualified"]
    assert (await replica_db.outreach_inbox_threads.find_one({"id": "t1"}))["tags"] == ["Unlinked"]
    assert (await replica_db.outreach_lead_tags.find_one({"name": "Qualified"}))["color"] == "#abcdef"
    assert (await tags.migrate_legacy_tags(replica_db, "w", "actor"))["migrated_threads"] == 0


async def test_native_dnc_preserves_current_original_aliases_and_blocks_import(replica_db):
    await seed(replica_db)
    await replica_db.outreach_leads.update_one({"id": "lead-0"}, {"$set": {"identifiers": {
        "normalized_url": "https://linkedin.com/in/original", "email": "old@example.com"}, "email": "new@example.com"}})
    await leads.block_lead("lead-0", leads.BlockLeadRequest(), current_user=USER, db=replica_db)
    await replica_db.outreach_campaigns.insert_one({"id": "draft", "workspace_id": "w", "status": "draft"})
    from outreach.core.lead_importer import LeadImporter
    result = await LeadImporter.ingest_leads([{"linkedin_url": "https://linkedin.com/in/original"},
        {"linkedin_url": "https://linkedin.com/in/another", "email": "new@example.com"}], "draft", "w", replica_db,
        skip_already_contacted=False, skip_do_not_contact=False)
    assert result["imported_count"] == 0 and result["skipped_count"] == 2
    listed = await leads.list_leads(skip=0, limit=50, current_user=USER, db=replica_db)
    assert next(row for row in listed["leads"] if row["id"] == "lead-0")["do_not_contact"]


async def test_native_followup_rechecks_dnc_and_retries_without_second_draft(replica_db):
    await seed(replica_db)
    await tags.assign_tags(replica_db, "w", ["lead-0"], TAG, "add")
    preview = await selection_preview(replica_db, "w", ["lead-0", "lead-1"], False)
    await leads.block_lead("lead-1", leads.BlockLeadRequest(), current_user=USER, db=replica_db)
    with pytest.raises(HTTPException) as failure:
        await create_selection_draft(replica_db, "w", "actor", ["lead-0", "lead-1"], False, "Next", "request", preview["review_digest"])
    assert failure.value.status_code == 409 and await replica_db.outreach_campaigns.count_documents({}) == 0
    preview = await selection_preview(replica_db, "w", ["lead-0", "lead-1"], False)
    assert preview["valid_count"] == 1
    args = (replica_db, "w", "actor", ["lead-0", "lead-1"], False, "Next", "request", preview["review_digest"])
    first = await create_selection_draft(*args)
    assert (await create_selection_draft(*args))["reused_request"]
    campaign = await replica_db.outreach_campaigns.find_one({"id": first["campaign_id"]})
    assert campaign["status"] == "draft" and campaign["sender_account_ids"] == []
    assert await replica_db.outreach_campaigns.count_documents({}) == 1
    enrolled = await replica_db.outreach_leads.find_one({"campaign_id": first["campaign_id"]})
    assert enrolled["source_metadata"]["origin_lead_id"] == "lead-0" and enrolled["tag_ids"] == [TAG]
    assert enrolled["assigned_account_id"] is None and await replica_db.outreach_execution_permissions.count_documents({}) == 0


@pytest.mark.parametrize("change", ["has_replied", "execution_state", "is_suppressed", "do_not_contact", "other_enrollment_reply"])
async def test_native_followup_allow_contacted_never_clears_reply_or_exclusion(replica_db, change):
    await seed(replica_db)
    if change == "other_enrollment_reply":
        await replica_db.outreach_leads.insert_one({"id": "old", "workspace_id": "w", "linkedin_url": "https://www.linkedin.com/in/alex-0", "has_replied": True})
    else:
        await replica_db.outreach_leads.update_one({"id": "lead-0"}, {"$set": {change: "replied" if change == "execution_state" else True}})
    preview = await selection_preview(replica_db, "w", ["lead-0"], True)
    assert preview["valid_count"] == 0
    with pytest.raises(HTTPException): await create_selection_draft(replica_db, "w", "actor", ["lead-0"], True, "Next", "request", preview["review_digest"])
    assert await replica_db.outreach_campaigns.count_documents({}) == 0


@pytest.mark.parametrize("role,expected", [("viewer", 403), ("editor", 201)])
async def test_native_http_permissions_and_shared_tag_routes(replica_db, role, expected):
    from fastapi import FastAPI
    import httpx
    from api.deps import get_current_user
    from db.mongo import get_db
    app = FastAPI()
    app.include_router(leads.router); app.include_router(inbox.router)
    app.dependency_overrides[get_current_user] = lambda: deepcopy(USER)
    app.dependency_overrides[get_db] = lambda: replica_db
    await replica_db.workspace_members.insert_one({"workspace_id": "w", "user_id": "actor", "role": role})
    await seed(replica_db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get('/leads/tags')).json()[0]["id"] == TAG
        response = await client.post('/leads/tags', json={"name": "New", "color": "#abcdef"})
        assert response.status_code == expected
        changed = await client.patch('/leads/lead-0/tags', json={"tag_id": TAG, "revision": 0, "operation": "add"})
        assert changed.status_code == (200 if role == "editor" else 403)
        inbox_tags = await client.get('/inbox/tags/list')
        assert inbox_tags.status_code == 200
        assert len(inbox_tags.json()) == (2 if role == "editor" else 1)


async def test_native_standalone_never_falls_back_to_partial_tag_writes(real_db):
    await seed(real_db)
    with pytest.raises(HTTPException) as failure: await tags.assign_tags(real_db, "w", ["lead-0", "lead-1"], TAG, "add")
    assert failure.value.status_code == 503
    assert await real_db.outreach_leads.count_documents({"tag_ids": TAG}) == 0


@pytest.mark.parametrize("field,value,dnc_field", [("linkedin_urn", "urn:li:member:new", "member_urn"),
    ("member_urn", "urn:li:member:new", "member_urn"), ("sales_lead_urn", "urn:li:fs_salesProfile:new", "sales_lead_urn"),
    ("vanity_name", "new-handle", "vanity_name")])
async def test_native_followup_retains_original_and_current_suppression_aliases(replica_db, field, value, dnc_field):
    from outreach.core.lead_importer import check_compound_suppression
    await seed(replica_db)
    await replica_db.outreach_leads.update_one({"id": "lead-0"}, {"$set": {
        "identifiers": {"normalized_url": "https://linkedin.com/in/original", "member_urn": "urn:li:member:old"}, field: value}})
    preview = await selection_preview(replica_db, "w", ["lead-0"], False)
    result = await create_selection_draft(replica_db, "w", "actor", ["lead-0"], False, "Next", "request", preview["review_digest"])
    copied = await replica_db.outreach_leads.find_one({"campaign_id": result["campaign_id"]})
    assert copied[field] == value and copied["identifiers"]["member_urn"] == "urn:li:member:old"
    await leads.add_do_not_contact(leads.DoNotContactRequest(**{dnc_field: value}), current_user=USER, db=replica_db)
    assert 0 in await check_compound_suppression("w", [copied], replica_db)
    await replica_db.outreach_do_not_contact.delete_many({})
    await leads.add_do_not_contact(leads.DoNotContactRequest(member_urn="urn:li:member:old"), current_user=USER, db=replica_db)
    assert 0 in await check_compound_suppression("w", [copied], replica_db)


async def test_native_multiple_current_and_saved_aliases_remain_independent(replica_db):
    from outreach.core.lead_importer import check_compound_suppression
    await seed(replica_db)
    await replica_db.outreach_leads.update_one({"id": "lead-0"}, {"$set": {
        "member_urn": "urn:li:member:current", "linkedin_urn": "urn:li:fsd_profile:new",
        "vanity_name": "discovered-handle", "email": "new@example.com",
        "identifiers": {"normalized_url": "https://linkedin.com/in/original", "member_urn": "urn:li:member:old", "email": "old@example.com", "vanity_name": "original-explicit"}}})
    preview = await selection_preview(replica_db, "w", ["lead-0"], False)
    result = await create_selection_draft(replica_db, "w", "actor", ["lead-0"], False, "Next", "request", preview["review_digest"])
    copied = await replica_db.outreach_leads.find_one({"campaign_id": result["campaign_id"]})
    await leads.block_lead("lead-0", leads.BlockLeadRequest(), current_user=USER, db=replica_db)
    for field, value in [("member_urn", "urn:li:member:current"), ("member_urn", "urn:li:fsd_profile:new"),
            ("member_urn", "urn:li:member:old"), ("vanity_name", "discovered-handle"), ("vanity_name", "original-explicit"),
            ("email", "new@example.com"), ("email", "old@example.com"), ("linkedin_url", "https://linkedin.com/in/original")]:
        assert 0 in await check_compound_suppression("w", [{field: value}], replica_db)
    assert 0 in await check_compound_suppression("w", [copied], replica_db)
    await replica_db.outreach_do_not_contact.delete_many({})
    await leads.add_do_not_contact(leads.DoNotContactRequest(member_urn="urn:li:member:old"), current_user=USER, db=replica_db)
    assert 0 in await check_compound_suppression("w", [copied], replica_db)
