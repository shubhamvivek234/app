"""Adversarial v2.65 reverification over disposable native Mongo records."""
from copy import deepcopy
import csv
import io
from datetime import datetime, timezone
import os

from fastapi import HTTPException
import pytest
from bson import ObjectId, Int64

from outreach.api import inbox, leads
from outreach.core import lead_tags as tags
from outreach.core.lead_selection import selection_preview, create_selection_draft
from outreach.core.email_finder import is_lead_email_available
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_tags_mongo import seed, USER, TAG

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Owned native Mongo is opt-in")]


async def duplicate_lead(db):
    await seed(db, count=1)
    row = await db.outreach_leads.find_one({"id": "lead-0"})
    row.pop("_id")
    row["linkedin_url"] = "https://linkedin.com/in/other-alex"
    await db.outreach_leads.insert_one(deepcopy(row))


async def test_reverify_bulk_duplicate_plus_missing_id_never_passes_count_check(replica_db):
    await duplicate_lead(replica_db)
    before = await replica_db.outreach_leads.find({}).to_list(10)
    with pytest.raises(HTTPException):
        await tags.assign_tags(replica_db, "w", ["lead-0", "missing"], TAG, "add")
    assert await replica_db.outreach_leads.find({}).to_list(10) == before


async def test_reverify_selection_rejects_duplicate_plus_missing_id(replica_db):
    await duplicate_lead(replica_db)
    with pytest.raises(HTTPException):
        await selection_preview(replica_db, "w", ["lead-0", "missing"], False)
    assert await replica_db.outreach_campaigns.count_documents({}) == 0


async def test_reverify_legacy_labels_keep_ambiguous_lead_link_for_review(replica_db):
    await duplicate_lead(replica_db)
    await replica_db.outreach_inbox_threads.insert_one({"workspace_id": "w", "id": "thread", "lead_id": "lead-0", "tags": ["Hot lead"]})
    result = await tags.migrate_legacy_tags(replica_db, "w", "actor")
    assert result["migrated_threads"] == 0 and len(result["skipped"]) == 1
    assert (await replica_db.outreach_inbox_threads.find_one({"id": "thread"}))["tags"] == ["Hot lead"]
    assert await replica_db.outreach_leads.count_documents({"tag_ids": TAG}) == 0


async def test_reverify_dnc_rejects_ambiguous_stored_lead(replica_db):
    await duplicate_lead(replica_db)
    with pytest.raises(HTTPException):
        await leads.block_lead("lead-0", leads.BlockLeadRequest(), current_user=USER, db=replica_db)
    assert await replica_db.outreach_do_not_contact.count_documents({}) == 0


@pytest.mark.parametrize("field,value", [("workspace_id", ["w", "foreign"]), ("id", ["thread", "foreign"])])
async def test_reverify_thread_detail_rejects_array_aliases(replica_db, field, value):
    row = {"id": "thread", "workspace_id": "w", "messages": [{"body": "foreign-private"}], "unread_count": 7}
    row[field] = value
    await replica_db.outreach_inbox_threads.insert_one(row)
    with pytest.raises(HTTPException) as failure:
        await inbox.get_thread("thread", current_user=USER, db=replica_db)
    assert failure.value.status_code == 404
    assert (await replica_db.outreach_inbox_threads.find_one({"_id": row["_id"]}))["unread_count"] == 7


async def test_reverify_draft_scope_mismatch_is_nonterminal_and_writes_nothing(replica_db):
    request = leads.LeadSelectionDraftRequest(lead_ids=["missing"], allow_contacted=False,
        name="Next", request_id="00000000-0000-4000-8000-000000000001", review_digest="a" * 64, request_scope="b" * 64)
    with pytest.raises(HTTPException) as failure:
        await leads.create_lead_selection_draft(request, current_user=USER, campaign_user=USER, db=replica_db)
    assert failure.value.status_code == 403
    assert await replica_db.outreach_campaigns.count_documents({}) == 0


@pytest.mark.parametrize("bad", [TAG, [{}], ["tag_" + "f" * 24]])
async def test_reverify_csv_malformed_or_orphan_assignments_are_explicitly_unavailable(replica_db, bad):
    await seed(replica_db, count=1)
    await replica_db.outreach_leads.update_one({"id": "lead-0"}, {"$set": {"tag_ids": bad}})
    response = await leads.export_leads(current_user=USER, db=replica_db)
    chunks = [chunk async for chunk in response.body_iterator]
    assert list(csv.DictReader(io.StringIO("".join(chunks))))[0]["tags"] == "Unavailable: tag assignments require review"


async def test_reverify_dense_legacy_migration_makes_bounded_resumable_progress(replica_db):
    from tests.test_outreach_lead_tags import tag_doc
    await seed(replica_db, count=100)
    definitions = [tag_doc("tag_" + f"{index + 1:024x}", name=f"Label {index}", name_normalized=f"label {index}") for index in range(50)]
    await replica_db.outreach_lead_tags.insert_many(definitions)
    names = [tag["name"] for tag in definitions]
    await replica_db.outreach_inbox_threads.insert_many([{"id": f"thread-{index:03}", "workspace_id": "w",
        "lead_id": f"lead-{index}", "tags": names} for index in range(100)])
    after, migrated, batches = "", 0, 0
    while True:
        result = await tags.migrate_legacy_tags(replica_db, "w", "actor", after)
        assert 1 <= result["migrated_threads"] <= 2 and not result["skipped"]
        assert result["next_after_id"] > after
        migrated += result["migrated_threads"]
        batches += 1
        after = result["next_after_id"]
        if not result["has_more"]:
            break
        assert batches < 100
    assert migrated == 100 and batches == 50
    assert await replica_db.outreach_inbox_threads.count_documents({"tags": {"$exists": True}}) == 0
    assert await replica_db.outreach_leads.count_documents({"tag_ids": {"$size": 50}, "tag_revision": 1}) == 100


async def test_reverify_replaced_physical_source_requires_new_review(replica_db):
    await seed(replica_db, count=1)
    preview = await selection_preview(replica_db, "w", ["lead-0"], False)
    source = await replica_db.outreach_leads.find_one({"id": "lead-0"})
    await replica_db.outreach_leads.delete_one({"_id": source.pop("_id")})
    await replica_db.outreach_leads.insert_one(source)
    with pytest.raises(HTTPException) as failure:
        await create_selection_draft(replica_db, "w", "actor", ["lead-0"], False, "Next", "new", preview["review_digest"])
    assert failure.value.status_code == 409 and await replica_db.outreach_campaigns.count_documents({}) == 0


@pytest.mark.parametrize("old_id,new_id", [(ObjectId("0123456789abcdef01234567"), "0123456789abcdef01234567"),
    ("0123456789abcdef01234567", ObjectId("0123456789abcdef01234567")), (1, Int64(1))])
async def test_reverify_physical_review_digest_preserves_native_bson_type(replica_db, old_id, new_id):
    await seed(replica_db, count=1)
    source = await replica_db.outreach_leads.find_one({"id": "lead-0"})
    await replica_db.outreach_leads.delete_many({})
    source["_id"] = old_id
    await replica_db.outreach_leads.insert_one(deepcopy(source))
    preview = await selection_preview(replica_db, "w", ["lead-0"], False)
    await replica_db.outreach_leads.delete_many({})
    source["_id"] = new_id
    await replica_db.outreach_leads.insert_one(deepcopy(source))
    with pytest.raises(HTTPException) as failure:
        await create_selection_draft(replica_db, "w", "actor", ["lead-0"], False, "Next", "new", preview["review_digest"])
    assert failure.value.status_code == 409 and await replica_db.outreach_campaigns.count_documents({}) == 0


@pytest.mark.parametrize("policy", [{"email_opted_out": True}, {"email_verification_status": "invalid"},
    {"email_verification_status": "unknown"}, {"email_verification_status": "accept_all"}, {"email_verification_status": "disposable"}])
async def test_reverify_followup_cannot_launder_negative_email_policy(replica_db, policy):
    await seed(replica_db, count=1)
    await replica_db.outreach_leads.update_one({"id": "lead-0"}, {"$set": {"email": "alex@example.test", **policy}})
    source = await replica_db.outreach_leads.find_one({"id": "lead-0"})
    assert not await is_lead_email_available(replica_db, "w", source)
    preview = await selection_preview(replica_db, "w", ["lead-0"], False)
    if policy.get("email_opted_out"):
        assert preview["valid_count"] == 0 and preview["rows"][0]["rejection_code"] == "suppressed"
    else:
        result = await create_selection_draft(replica_db, "w", "actor", ["lead-0"], False, "Next", "new", preview["review_digest"])
        enrolled = await replica_db.outreach_leads.find_one({"campaign_id": result["campaign_id"]})
        assert enrolled["email_verification_status"] == policy["email_verification_status"]
        assert not await is_lead_email_available(replica_db, "w", enrolled)


async def test_reverify_negative_email_policy_change_invalidates_preview(replica_db):
    await seed(replica_db, count=1)
    preview = await selection_preview(replica_db, "w", ["lead-0"], False)
    await replica_db.outreach_leads.update_one({"id": "lead-0"}, {"$set": {"email_verification_status": "invalid"}})
    with pytest.raises(HTTPException) as failure:
        await create_selection_draft(replica_db, "w", "actor", ["lead-0"], False, "Next", "new", preview["review_digest"])
    assert failure.value.status_code == 409 and await replica_db.outreach_campaigns.count_documents({}) == 0


async def test_reverify_followup_preserves_original_email_evidence_and_cross_enrollment_optout(replica_db):
    await seed(replica_db, count=1)
    evidence = {"email": "alex@example.test", "email_verification_status": "valid", "email_source": "hunter_found",
        "email_source_urls": ["https://example.test/team"], "email_verified_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "email_found_at": datetime(2026, 9, 30, tzinfo=timezone.utc)}
    await replica_db.outreach_leads.update_one({"id": "lead-0"}, {"$set": evidence})
    source = await replica_db.outreach_leads.find_one({"id": "lead-0"})
    preview = await selection_preview(replica_db, "w", ["lead-0"], False)
    result = await create_selection_draft(replica_db, "w", "actor", ["lead-0"], False, "Next", "new", preview["review_digest"])
    enrolled = await replica_db.outreach_leads.find_one({"campaign_id": result["campaign_id"]})
    assert {key: enrolled[key] for key in evidence} == {key: source[key] for key in evidence}
    await replica_db.outreach_leads.insert_one({"id": "old-optout", "workspace_id": "w", "email": evidence["email"], "email_opted_out": True})
    assert (await selection_preview(replica_db, "w", ["lead-0"], True))["valid_count"] == 0


@pytest.mark.parametrize("target", ["lead", "thread"])
async def test_reverify_inbox_tag_controls_reject_duplicate_link_identity(replica_db, target):
    await seed(replica_db, count=1)
    thread = {"id": "thread", "workspace_id": "w", "lead_id": "lead-0", "unread_count": 3}
    await replica_db.outreach_inbox_threads.insert_one(deepcopy(thread))
    if target == "lead":
        lead = await replica_db.outreach_leads.find_one({"id": "lead-0"})
        lead.pop("_id")
        await replica_db.outreach_leads.insert_one(lead)
    else:
        await replica_db.outreach_inbox_threads.insert_one(deepcopy(thread))
    with pytest.raises(HTTPException) as failure:
        await inbox.toggle_thread_tag("thread", inbox.ToggleTagRequest(tag_id=TAG, operation="add", revision=0), current_user=USER, db=replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_leads.count_documents({"tag_ids": TAG}) == 0


@pytest.mark.parametrize("role,context_status,draft_status", [(None, 200, 403), ("viewer", 200, 403), ("editor", 200, 200)])
async def test_reverify_http_context_and_draft_scope_permissions(replica_db, role, context_status, draft_status):
    from fastapi import FastAPI
    import httpx
    from api.deps import get_current_user
    from db.mongo import get_db
    app = FastAPI()
    app.include_router(leads.router)
    app.dependency_overrides[get_current_user] = lambda: deepcopy(USER)
    app.dependency_overrides[get_db] = lambda: replica_db
    if role:
        await replica_db.workspace_members.insert_one({"workspace_id": "w", "user_id": "actor", "role": role})
    await seed(replica_db, count=1)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        context = await client.get("/leads/selection/context")
        assert context.status_code == context_status
        scope = context.json().get("request_scope", "b" * 64)
        if role is None:
            # Shared auth legitimately creates a personal workspace. Its opaque
            # context must not authorize a request bound to the stale workspace.
            assert scope != leads._selection_request_scope(USER)
            scope = leads._selection_request_scope(USER)
        preview = await selection_preview(replica_db, "w", ["lead-0"], False)
        payload = {"lead_ids": ["lead-0"], "name": "Next", "allow_contacted": False,
            "review_digest": preview["review_digest"], "request_id": "00000000-0000-4000-8000-000000000001", "request_scope": scope}
        assert (await client.post("/leads/selection/draft", json=payload)).status_code == draft_status
        if role == "editor":
            payload["request_scope"] = "c" * 64
            assert (await client.post("/leads/selection/draft", json=payload)).status_code == 403
            assert await replica_db.outreach_campaigns.count_documents({}) == 1
