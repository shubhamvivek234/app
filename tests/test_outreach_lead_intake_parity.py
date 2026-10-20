"""Direct intake keeps reviewed names, fields, exclusions and identity decisions."""
import pytest
import httpx
from fastapi import FastAPI

from api.deps import get_current_user
from db.mongo import get_db
from outreach.api.leads import ImportCSVRequest, import_leads_csv, router
from outreach.core.lead_importer import LeadImporter
from tests.outreach_memory import Database


USER = {"user_id": "actor", "default_workspace_id": "workspace"}


def database():
    return Database(outreach_campaigns=[{"id": "campaign", "workspace_id": "workspace", "status": "draft"}])


@pytest.mark.asyncio
@pytest.mark.parametrize("nested", [{}, {"email": "alias@example.invalid"},
    {"normalized_url": "https://linkedin.com/in/other", "vanity_name": "other"}])
async def test_current_profile_dedupes_even_with_partial_or_conflicting_saved_identifiers(nested):
    rows = [{"linkedin_url": url, "first_name": "Alice", "identifiers": {
        key: f"{value}{index}" for key, value in nested.items()}}
        for index, url in enumerate(("https://linkedin.com/in/alice", "https://www.linkedin.com/in/alice"))]
    db = database()
    preview = await LeadImporter.preview_leads(rows, "campaign", "workspace", db)
    assert preview["valid_count"] == 1
    assert preview["rows"][1]["rejection_code"] == "duplicate_batch"
    imported = await LeadImporter.ingest_leads(rows, "campaign", "workspace", db)
    assert imported["imported_count"] == 1
    assert imported["duplicates_count"] == 1


@pytest.mark.asyncio
async def test_current_email_dedupes_despite_distinct_saved_aliases():
    rows = [{"linkedin_url": f"https://linkedin.com/in/{name}", "first_name": name,
        "email": email, "identifiers": {"normalized_url": f"https://linkedin.com/in/{name}"}}
        for name, email in (("alice", " SHARED@example.invalid "), ("bob", "shared@example.invalid"))]
    db = database()
    assert (await LeadImporter.preview_leads(rows, "campaign", "workspace", db))["valid_count"] == 1
    assert (await LeadImporter.ingest_leads(rows, "campaign", "workspace", db))["imported_count"] == 1


@pytest.mark.asyncio
async def test_saved_aliases_still_dedupe_when_current_profiles_differ():
    rows = [{"linkedin_url": f"https://linkedin.com/in/{name}", "first_name": name,
        "identifiers": {"member_urn": "urn:li:member:123456"}} for name in ("alice", "bob")]
    db = database()
    assert (await LeadImporter.preview_leads(rows, "campaign", "workspace", db))["valid_count"] == 1
    result = await LeadImporter.ingest_leads(rows, "campaign", "workspace", db)
    assert result["imported_count"] == 1
    assert db.outreach_leads.docs[0]["identifiers"]["normalized_url"] == rows[0]["linkedin_url"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field,current,saved", [
    ("member_urn", " urn:li:member:123456 ", "urn:li:member:999999"),
    ("email", " SHARED@example.invalid ", " OLD@example.invalid "),
    ("sales_lead_urn", " urn:li:salesProfile:current ", "urn:li:salesProfile:old"),
    ("vanity_name", " discovered-alice ", "old-alice"),
])
async def test_separate_imports_retain_current_and_saved_identities(field, current, saved):
    db = database()
    first = {"linkedin_url": "https://linkedin.com/in/alice", "first_name": "Alice",
        field: current, "identifiers": {field: saved}}
    preview = await LeadImporter.preview_leads([first], "campaign", "workspace", db)
    assert preview["valid_count"] == 1
    assert (await LeadImporter.ingest_leads(preview["rows"], "campaign", "workspace", db))["imported_count"] == 1
    for value in (current.strip().lower() if field in {"email", "vanity_name"} else current.strip(),
                  saved.strip().lower() if field in {"email", "vanity_name"} else saved.strip()):
        next_row = {"linkedin_url": "https://linkedin.com/in/bob", "first_name": "Bob", field: value}
        checked = await LeadImporter.preview_leads([next_row], "campaign", "workspace", db)
        admitted = await LeadImporter.ingest_leads([next_row], "campaign", "workspace", db)
        assert checked["valid_count"] == admitted["imported_count"] == 0
        assert checked["rows"][0]["rejection_code"] == "duplicate_campaign"
        assert admitted["duplicates_count"] == 1
    assert len(db.outreach_leads.docs) == 1


@pytest.mark.asyncio
async def test_csv_explicit_name_policy_matches_preview_and_preserves_rejected_totals():
    csv = "linkedin_url,first_name,location\nhttps://linkedin.com/in/alice,Alice,Sydney\nhttps://linkedin.com/in/unnamed,,Delhi\nhttps://invalid.example/in/bad,Bad,London\n"
    db = database()
    preview = await LeadImporter.preview_leads(LeadImporter.parse_csv_content(csv, include_invalid=True),
        "campaign", "workspace", db, require_name=True)
    result = await import_leads_csv(ImportCSVRequest(campaign_id="campaign", csv_text=csv, require_name=True),
        current_user=USER, db=db)
    assert result["total_submitted"] == preview["total_submitted"] == 3
    assert result["imported_count"] == preview["valid_count"] == 1
    assert {r["rejection_code"] for r in result["rejections"]} == {"invalid_url", "missing_name"}
    assert db.outreach_leads.docs[0]["location"] == "Sydney"


@pytest.mark.asyncio
async def test_csv_omitted_name_policy_retains_legacy_optional_names():
    db = database()
    result = await import_leads_csv(ImportCSVRequest(campaign_id="campaign", csv_text="linkedin_url\nhttps://linkedin.com/in/unnamed"),
        current_user=USER, db=db)
    assert result["imported_count"] == 1


@pytest.mark.asyncio
async def test_preview_to_edited_staging_preserves_location_and_explicit_empty_name():
    rows = [{"linkedin_url": "https://linkedin.com/in/alice", "raw_first_name": "Alice", "first_name": "Alice",
        "cleaned_first_name": "", "location": "Sydney", "email": "alice@example.invalid",
        "phone": "+123", "custom_variables": {"region": "NSW"}}]
    db = database()
    preview = await LeadImporter.preview_leads(rows, "campaign", "workspace", db, require_name=True)
    assert preview["valid_count"] == 0
    assert preview["rows"][0]["rejection_code"] == "missing_name"
    assert preview["rows"][0]["location"] == "Sydney"
    corrected = {**preview["rows"][0], "first_name": "Ally", "cleaned_first_name": "Ally"}
    reviewed = await LeadImporter.preview_leads([corrected], "campaign", "workspace", db, require_name=True)
    assert reviewed["valid_count"] == 1
    result = await LeadImporter.ingest_leads(reviewed["rows"], "campaign", "workspace", db, require_name=True)
    assert result["imported_count"] == 1
    saved = db.outreach_leads.docs[0]
    assert saved["first_name"] == "Ally" and saved["raw_first_name"] == "Alice"
    assert saved["location"] == "Sydney" and saved["custom_variables"] == {"region": "NSW"}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["email", "profile"])
async def test_direct_preview_always_reports_mandatory_suppression(kind):
    db = database()
    rows = [{"linkedin_url": "https://linkedin.com/in/alice", "first_name": "Alice", "email": "alice@example.invalid"}]
    collection = db.outreach_email_suppressions if kind == "email" else db.outreach_do_not_contact
    await collection.insert_one({"workspace_id": "workspace", **({"email": rows[0]["email"]} if kind == "email" else {"linkedin_url": rows[0]["linkedin_url"]})})
    result = await LeadImporter.preview_leads(rows, "campaign", "workspace", db, skip_do_not_contact=False)
    assert result["valid_count"] == 0
    assert result["rows"][0]["rejection_code"] == ("email_suppressed" if kind == "email" else "do_not_contact")


@pytest.mark.asyncio
async def test_edited_preview_http_enforces_workspace_and_search_source_hold():
    db = database()
    await db.workspaces.insert_one({"workspace_id": "workspace", "owner_id": "actor"})
    await db.workspace_members.insert_one({"workspace_id": "workspace", "user_id": "actor", "role": "admin"})
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db] = lambda: db
    row = {"linkedin_url": "https://linkedin.com/in/alice", "first_name": "Alice", "location": "Sydney"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        valid = await client.post("/leads/preview-staged", json={"campaign_id": "campaign", "leads": [row], "require_name": True})
        assert valid.status_code == 200 and valid.json()["rows"][0]["location"] == "Sydney"
        foreign = await client.post("/leads/preview-staged", json={"campaign_id": "foreign", "leads": [row]})
        assert foreign.status_code == 404
        held = await client.post("/leads/preview-staged", json={"campaign_id": "campaign", "leads": [{**row, "import_job_id": "saved-search"}]})
        assert held.status_code == 409
