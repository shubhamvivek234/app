"""Tag identity, metadata-only assignments, compatibility and selection contracts."""
from copy import deepcopy
from unittest.mock import AsyncMock

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from outreach.api import leads, inbox
from outreach.core import lead_tags as tags
from outreach.core.lead_selection import selection_preview, create_selection_draft
from tests.outreach_memory import Database

USER = {"user_id": "actor", "default_workspace_id": "w"}
TAG = "tag_" + "a" * 24
OTHER_TAG = "tag_" + "b" * 24


def tag_doc(identifier=TAG, **extra):
    return {"id": identifier, "workspace_id": "w", "name": "Hot lead", "name_normalized": "hot lead",
            "color": "#ef4444", "revision": 1, **extra}


@pytest.mark.parametrize("name,display,normalized", [("  Hot   LEAD ", "Hot LEAD", "hot lead"),
    ("Ｈｏｔ", "Hot", "hot"), ("Straße", "Straße", "strasse")])
def test_normalized_name_identity(name, display, normalized):
    assert tags.clean_tag_name(name) == (display, normalized)


@pytest.mark.parametrize("name", [" ", "\x01bad", "x" * 61, "\u200bbad"])
def test_invalid_names_rejected(name):
    with pytest.raises(HTTPException): tags.clean_tag_name(name)


@pytest.mark.parametrize("revision", [True, 1.0, "1", -1])
def test_client_revision_is_strict(revision):
    with pytest.raises(ValidationError): leads.LeadTagMutationRequest(tag_id=TAG, operation="add", revision=revision)


@pytest.mark.asyncio
async def test_read_does_not_seed_and_create_is_case_insensitive():
    db = Database()
    assert await leads.list_lead_tags(current_user=USER, db=db) == []
    assert db.outreach_lead_tags.docs == []
    created = await leads.create_lead_tag(leads.CreateLeadTagRequest(name="  Hot lead "), current_user=USER, db=db)
    assert len(created["id"]) == 28 and "workspace_id" not in created
    with pytest.raises(HTTPException) as failure:
        await leads.create_lead_tag(leads.CreateLeadTagRequest(name="HOT LEAD"), current_user=USER, db=db)
    assert failure.value.status_code == 409
    assert len(db.outreach_lead_tags.docs) == 1


@pytest.mark.asyncio
async def test_rename_recolor_archive_preserve_identity_and_assignments():
    db = Database(outreach_lead_tags=[tag_doc()], outreach_leads=[{"id": "lead", "workspace_id": "w", "tag_ids": [TAG]}])
    changed = await tags.edit_tag(db, "w", TAG, 1, "Qualified", "#00ff00")
    assert changed["id"] == TAG and changed["revision"] == 2
    await tags.hydrate_lead_tags(db, "w", db.outreach_leads.docs)
    assert db.outreach_leads.docs[0]["tags"][0]["name"] == "Qualified"
    with pytest.raises(HTTPException): await tags.edit_tag(db, "w", TAG, 1, "Stale", "#00ff00")
    await tags.edit_tag(db, "w", TAG, 2, archive=True)
    await tags.hydrate_lead_tags(db, "w", db.outreach_leads.docs)
    assert db.outreach_leads.docs[0]["tag_ids"] == [TAG] and db.outreach_leads.docs[0]["tags"] == []
    with pytest.raises(HTTPException): await tags.assign_tags(db, "w", ["lead"], TAG, "add")
    assert (await tags.assign_tags(db, "w", ["lead"], TAG, "remove"))["modified_count"] == 1


@pytest.mark.asyncio
async def test_assignment_noop_and_stale_revision_do_not_clobber():
    db = Database(outreach_lead_tags=[tag_doc()], outreach_leads=[{"id": "lead", "workspace_id": "w", "execution_state": "paused", "has_replied": True}])
    result = await tags.assign_tags(db, "w", ["lead"], TAG, "add", 0)
    assert result["modified_count"] == 1
    assert (await tags.assign_tags(db, "w", ["lead"], TAG, "add", 1))["modified_count"] == 0
    with pytest.raises(HTTPException): await tags.assign_tags(db, "w", ["lead"], TAG, "remove", 0)
    row = db.outreach_leads.docs[0]
    assert row["tag_revision"] == 1 and row["tag_ids"] == [TAG]
    assert row["execution_state"] == "paused" and row["has_replied"] is True
    assert db.outreach_execution_permissions.docs == []


@pytest.mark.asyncio
async def test_bulk_unknown_scope_does_not_mutate_existing_lead():
    db = Database(outreach_lead_tags=[tag_doc()], outreach_leads=[{"id": "lead", "workspace_id": "w"}, {"id": "foreign", "workspace_id": "elsewhere"}])
    with pytest.raises(HTTPException) as failure: await tags.assign_tags(db, "w", ["lead", "foreign"], TAG, "add")
    assert failure.value.status_code == 404
    assert "tag_ids" not in db.outreach_leads.docs[0]


@pytest.mark.parametrize("bad", [None, "x", [TAG, TAG], [True], [TAG] * 51])
@pytest.mark.asyncio
async def test_malformed_assignments_fail_before_mutation(bad):
    db = Database(outreach_lead_tags=[tag_doc()], outreach_leads=[{"id": "lead", "workspace_id": "w", "tag_ids": bad}])
    before = deepcopy(db.outreach_leads.docs)
    with pytest.raises(HTTPException): await tags.assign_tags(db, "w", ["lead"], TAG, "add")
    assert db.outreach_leads.docs == before


@pytest.mark.asyncio
async def test_inbox_shared_assignment_and_preserved_legacy_labels():
    db = Database(outreach_lead_tags=[tag_doc()], outreach_leads=[{"id": "lead", "workspace_id": "w"}],
        outreach_inbox_threads=[{"id": "thread", "workspace_id": "w", "lead_id": "lead", "tags": ["Old label"]}])
    result = await inbox.toggle_thread_tag("thread", inbox.ToggleTagRequest(tag_id=TAG, operation="add", revision=0), current_user=USER, db=db)
    assert result["tag_ids"] == [TAG] and result["legacy_tags"] == ["Old label"]
    thread = await inbox.get_thread("thread", current_user=USER, db=db)
    assert thread["tags"][0]["id"] == TAG
    assert db.outreach_inbox_threads.docs[0]["tags"] == ["Old label"]
    db.outreach_inbox_threads.docs[0].pop("lead_id")
    with pytest.raises(HTTPException) as failure: await inbox.toggle_thread_tag("thread", inbox.ToggleTagRequest(tag_id=TAG, operation="add", revision=0), current_user=USER, db=db)
    assert failure.value.status_code == 409


@pytest.mark.asyncio
async def test_failed_transaction_never_reports_success(monkeypatch):
    from outreach.core.suppression import SuppressionUnavailable
    monkeypatch.setattr("outreach.core.suppression.mutate_suppression", AsyncMock(side_effect=SuppressionUnavailable()))
    with pytest.raises(HTTPException) as failure: await tags.create_tag(Database(), "w", "actor", "New", "#000000")
    assert failure.value.status_code == 503


@pytest.mark.asyncio
async def test_selection_requires_review_and_keeps_senders_and_authority_empty():
    db = Database(outreach_lead_tags=[tag_doc()], outreach_leads=[{"id": "lead", "workspace_id": "w",
        "linkedin_url": "https://linkedin.com/in/alex", "first_name": "Alex", "tag_ids": [TAG]}])
    preview = await selection_preview(db, "w", ["lead"], False)
    assert preview["valid_count"] == 1
    request = (db, "w", "actor", ["lead"], False, "Follow-up", "request", preview["review_digest"])
    result = await create_selection_draft(*request)
    assert result["imported_count"] == 1
    assert (await create_selection_draft(*request))["reused_request"]
    campaign = db.outreach_campaigns.docs[0]
    assert campaign["status"] == "draft" and campaign["sender_account_ids"] == []
    enrolled = next(row for row in db.outreach_leads.docs if row.get("campaign_id") == result["campaign_id"])
    assert enrolled["tag_ids"] == [TAG] and enrolled["assigned_account_id"] is None
    assert enrolled["source_metadata"]["origin_lead_id"] == "lead"
    assert db.outreach_execution_permissions.docs == []
    assert len(db.outreach_campaigns.docs) == 1


@pytest.mark.asyncio
async def test_selection_changed_source_denies_before_draft():
    db = Database(outreach_leads=[{"id": "lead", "workspace_id": "w", "linkedin_url": "https://linkedin.com/in/alex"}])
    preview = await selection_preview(db, "w", ["lead"], True)
    db.outreach_leads.docs[0]["has_replied"] = True
    with pytest.raises(HTTPException) as failure: await create_selection_draft(db, "w", "actor", ["lead"], True, "Follow-up", "request", preview["review_digest"])
    assert failure.value.status_code == 409 and db.outreach_campaigns.docs == []


@pytest.mark.asyncio
async def test_archived_assignments_can_be_removed_to_free_capacity():
    identifiers = ["tag_" + f"{index:024x}" for index in range(50)]
    db = Database(outreach_lead_tags=[tag_doc(identifier, name=f"Tag {index}", name_normalized=f"tag {index}") for index, identifier in enumerate(identifiers)],
        outreach_leads=[{"id": "lead", "workspace_id": "w", "tag_ids": identifiers}])
    await tags.edit_tag(db, "w", identifiers[0], 1, archive=True)
    row = deepcopy(db.outreach_leads.docs[0])
    await tags.hydrate_lead_tags(db, "w", [row])
    assert len(row["tags"]) == 49 and row["archived_tags"][0]["id"] == identifiers[0]
    await tags.assign_tags(db, "w", ["lead"], identifiers[0], "remove", 0)
    new = await tags.create_tag(db, "w", "actor", "Replacement", "#123456")
    await tags.assign_tags(db, "w", ["lead"], new["id"], "add", 1)
    assert len(db.outreach_leads.docs[0]["tag_ids"]) == 50
    assert db.outreach_lead_tags.docs[0]["archived_at"]


@pytest.mark.asyncio
async def test_reply_review_retains_the_candidate_identity_query():
    from unittest.mock import Mock
    db = Database(outreach_leads=[{"id": "lead", "workspace_id": "w", "linkedin_url": "https://linkedin.com/in/alex"}])
    db.outreach_leads.find = Mock(wraps=db.outreach_leads.find)
    await selection_preview(db, "w", ["lead"], False)
    reply_query = next(call.args[0] for call in db.outreach_leads.find.call_args_list if "$and" in call.args[0])
    assert reply_query["workspace_id"] == "w" and "$or" in reply_query
    assert any("identifiers.normalized_url" in clause or "linkedin_url" in clause for clause in reply_query["$or"])
