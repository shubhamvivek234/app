"""Current intake fixes through actual transactions on an owned local replica."""
import os

import pytest

from outreach.api.leads import ImportCSVRequest, ImportStagedRequest, import_leads_csv, import_leads_staged, preview_edited_leads
from outreach.core.lead_importer import LeadImporter
from tests.outreach_native import replica_server, replica_db  # noqa: F401


pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv("OUTREACH_TEST_LOCAL_MONGO") != "1", reason="Owned native Mongo is opt-in")]
USER = {"user_id": "actor", "default_workspace_id": "workspace"}


async def campaign(db):
    await db.outreach_campaigns.insert_one({"id": "campaign", "workspace_id": "workspace", "status": "draft", "leads_count": 0})


@pytest.mark.parametrize("kind", ["empty", "conflicting", "email"])
async def test_one_current_identity_cannot_create_two_enrollments(replica_db, kind):
    await campaign(replica_db)
    rows = [{"linkedin_url": f"https://{'www.' if index else ''}linkedin.com/in/alice", "first_name": "Alice", "identifiers": {}}
        for index in range(2)]
    if kind == "conflicting":
        for index, row in enumerate(rows): row["identifiers"] = {"normalized_url": f"https://linkedin.com/in/old-{index}"}
    if kind == "email":
        rows[1]["linkedin_url"] = "https://linkedin.com/in/bob"
        rows[0]["email"] = " SHARED@example.invalid "
        rows[1]["email"] = "shared@example.invalid"
    preview = await LeadImporter.preview_leads(rows, "campaign", "workspace", replica_db)
    result = await LeadImporter.ingest_leads(rows, "campaign", "workspace", replica_db)
    assert preview["valid_count"] == result["imported_count"] == result["duplicates_count"] == 1
    assert await replica_db.outreach_leads.count_documents({}) == 1
    assert await replica_db.outreach_event_outbox.count_documents({}) == 1
    assert (await replica_db.outreach_campaigns.find_one({"id": "campaign"}))["leads_count"] == 1


async def test_strict_csv_policy_and_rejection_accounting_are_committed(replica_db):
    await campaign(replica_db)
    result = await import_leads_csv(ImportCSVRequest(campaign_id="campaign", require_name=True,
        csv_text="linkedin_url,first_name\nhttps://linkedin.com/in/alice,Alice\nhttps://linkedin.com/in/blank,\nbad,Bad"),
        current_user=USER, db=replica_db)
    assert result["total_submitted"] == 3 and result["imported_count"] == 1
    assert {r["rejection_code"] for r in result["rejections"]} == {"missing_name", "invalid_url"}
    assert await replica_db.outreach_leads.count_documents({}) == 1


async def test_edited_review_rechecks_exclusions_and_commit_never_trusts_client_status(replica_db):
    await campaign(replica_db)
    rows = [{"linkedin_url": "https://linkedin.com/in/alice", "first_name": "", "raw_first_name": "Alice",
        "cleaned_first_name": "", "location": "Sydney", "status": "valid"}]
    request = ImportStagedRequest(campaign_id="campaign", require_name=True, leads=rows)
    preview = await preview_edited_leads(request, current_user=USER, db=replica_db)
    assert preview["valid_count"] == 0 and preview["rows"][0]["rejection_code"] == "missing_name"
    assert (await import_leads_staged(request, current_user=USER, db=replica_db))["imported_count"] == 0
    fixed = {**preview["rows"][0], "first_name": "Ally", "cleaned_first_name": "Ally"}
    request = ImportStagedRequest(campaign_id="campaign", require_name=True, leads=[fixed])
    reviewed = await preview_edited_leads(request, current_user=USER, db=replica_db)
    assert reviewed["valid_count"] == 1
    await replica_db.outreach_do_not_contact.insert_one({"workspace_id": "workspace", "linkedin_url": fixed["linkedin_url"]})
    assert (await import_leads_staged(request, current_user=USER, db=replica_db))["imported_count"] == 0
    await replica_db.outreach_do_not_contact.delete_many({})
    assert (await import_leads_staged(request, current_user=USER, db=replica_db))["imported_count"] == 1
    saved = await replica_db.outreach_leads.find_one({})
    assert saved["first_name"] == "Ally" and saved["raw_first_name"] == "Alice" and saved["location"] == "Sydney"


@pytest.mark.parametrize("field,current,saved", [
    ("member_urn", " urn:li:member:123456 ", "urn:li:member:999999"),
    ("email", " SHARED@example.invalid ", " OLD@example.invalid "),
    ("sales_lead_urn", " urn:li:salesProfile:current ", "urn:li:salesProfile:old"),
    ("vanity_name", " discovered-alice ", "old-alice"),
])
@pytest.mark.parametrize("round_trip", [False, True])
async def test_separate_transactions_preserve_current_and_saved_aliases(replica_db, field, current, saved, round_trip):
    await campaign(replica_db)
    first = {"linkedin_url": "https://linkedin.com/in/alice", "first_name": "Alice",
        field: current, "identifiers": {field: saved}}
    preview = await LeadImporter.preview_leads([first], "campaign", "workspace", replica_db)
    assert preview["valid_count"] == 1
    assert (await LeadImporter.ingest_leads(preview["rows"] if round_trip else [first],
        "campaign", "workspace", replica_db))["imported_count"] == 1
    canonical_current = current.strip().lower() if field in {"email", "vanity_name"} else current.strip()
    canonical_saved = saved.strip().lower() if field in {"email", "vanity_name"} else saved.strip()
    stored = await replica_db.outreach_leads.find_one({})
    assert stored[field] == canonical_current
    assert stored["identifiers"][field] == canonical_saved
    if field == "member_urn":
        assert stored["linkedin_urn"] == canonical_current
    for value in (canonical_current, canonical_saved):
        later = {"linkedin_url": "https://linkedin.com/in/bob", "first_name": "Bob", field: value}
        checked = await LeadImporter.preview_leads([later], "campaign", "workspace", replica_db)
        admitted = await LeadImporter.ingest_leads([later], "campaign", "workspace", replica_db)
        assert checked["valid_count"] == admitted["imported_count"] == 0
        assert admitted["duplicates_count"] == 1
    assert await replica_db.outreach_leads.count_documents({}) == 1
    assert await replica_db.outreach_event_outbox.count_documents({}) == 1
    assert (await replica_db.outreach_campaigns.find_one({"id": "campaign"}))["leads_count"] == 1


async def test_current_member_and_email_survive_contacted_cross_campaign_checks(replica_db):
    from datetime import datetime, timezone

    await campaign(replica_db)
    await replica_db.outreach_campaigns.insert_one({"id": "later", "workspace_id": "workspace", "status": "draft", "leads_count": 0})
    first = {"linkedin_url": "https://linkedin.com/in/alice", "first_name": "Alice",
        "member_urn": "urn:li:member:123456", "email": " SHARED@example.invalid ",
        "identifiers": {"member_urn": "urn:li:member:999999", "email": "old@example.invalid"}}
    assert (await LeadImporter.ingest_leads([first], "campaign", "workspace", replica_db))["imported_count"] == 1
    await replica_db.outreach_leads.update_one({}, {"$set": {"last_action_at": datetime.now(timezone.utc)}})
    for alias in ({"member_urn": "urn:li:member:123456"}, {"email": "shared@example.invalid"}):
        row = {"linkedin_url": "https://linkedin.com/in/bob", "first_name": "Bob", **alias}
        checked = await LeadImporter.preview_leads([row], "later", "workspace", replica_db)
        result = await LeadImporter.ingest_leads([row], "later", "workspace", replica_db, include_rejections=True)
        assert checked["rows"][0]["rejection_code"] == "duplicate_contacted"
        assert result["imported_count"] == 0 and result["rejections"][0]["rejection_code"] == "duplicate_contacted"
    assert await replica_db.outreach_leads.count_documents({"campaign_id": "later"}) == 0
