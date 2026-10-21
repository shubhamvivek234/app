"""
Automated test suite for Phase 3: Lead Sourcing, Ingestion & Deduplication CRM.
"""
import os
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from unittest.mock import AsyncMock
from tests.outreach_memory import Database
from outreach.core.lead_importer import (
    LeadImporter,
    normalize_linkedin_url,
    detect_csv_headers,
)
from outreach.api.leads import (
    ImportCSVRequest,
    DoNotContactRequest,
    import_leads_csv,
    list_leads,
    delete_lead,
    add_do_not_contact,
)


def test_normalize_linkedin_url():
    """Verify URL cleaning strips tracking params, enforces https, and lowercases paths."""
    raw1 = "http://www.linkedin.com/in/john-doe/?miniProfileUrn=urn%3Ali%3A123"
    assert normalize_linkedin_url(raw1) == "https://www.linkedin.com/in/john-doe"

    raw2 = "linkedin.com/in/Jane-Smith/"
    assert normalize_linkedin_url(raw2) == "https://linkedin.com/in/jane-smith"


def test_detect_csv_headers_and_parse():
    """Verify automatic CSV header discovery and custom attribute preservation."""
    sample_csv = """First Name,Last Name,Company Name,Job Title,LinkedIn Profile URL,ARR,Industry
John,Doe,Acme Corp,CTO,https://linkedin.com/in/johndoe,$10M,SaaS
Jane,Smith,Stripe,VP Product,https://linkedin.com/in/janesmith,$1B,Fintech
Invalid,Lead,None,None,http://twitter.com/notlinkedin,0,None
"""
    parsed = LeadImporter.parse_csv_content(sample_csv)
    assert len(parsed) == 2  # Invalid row filtered out
    assert parsed[0]["first_name"] == "John"
    assert parsed[0]["company_name"] == "Acme Corp"
    assert parsed[0]["linkedin_url"] == "https://linkedin.com/in/johndoe"
    assert parsed[0]["custom_variables"]["ARR"] == "$10M"
    assert parsed[0]["custom_variables"]["Industry"] == "SaaS"


def test_parse_csv_full_name_split():
    """Verify CSV with a single Full Name column automatically splits into first_name and last_name."""
    sample_csv = """Full Name,Company,Title,LinkedIn URL,Segment
Ada Lovelace,Analytical Engine,Chief Mathematician,https://linkedin.com/in/adalovelace,Enterprise
Grace Murray Hopper,US Navy,Rear Admiral,https://linkedin.com/in/gracehopper,Gov
"""
    parsed = LeadImporter.parse_csv_content(sample_csv)
    assert len(parsed) == 2
    assert parsed[0]["first_name"] == "Ada"
    assert parsed[0]["last_name"] == "Lovelace"
    assert parsed[0]["company_name"] == "Analytical Engine"
    assert parsed[0]["custom_variables"]["Segment"] == "Enterprise"
    assert parsed[1]["first_name"] == "Grace"
    assert parsed[1]["last_name"] == "Murray Hopper"


@pytest.mark.asyncio
async def test_lead_deduplication_and_ingestion():
    """Verify deduplication skips duplicates in campaign and blocks Do-Not-Contact URLs."""
    mock_db = Database(outreach_campaigns=[{"id": "camp_test", "workspace_id": "ws_test", "status": "draft"}],
        outreach_leads=[{"workspace_id": "ws_test", "campaign_id": "camp_test", "linkedin_url": "https://linkedin.com/in/existing"}],
        outreach_do_not_contact=[{"workspace_id": "ws_test", "linkedin_url": "https://linkedin.com/in/vip-dnc"}])
    leads_batch = [
        {"linkedin_url": "https://linkedin.com/in/new-lead-1", "first_name": "New 1"},
        {"linkedin_url": "https://linkedin.com/in/existing", "first_name": "Duplicate In Camp"},
        {"linkedin_url": "https://linkedin.com/in/vip-dnc", "first_name": "Blacklisted DNC"},
        {"linkedin_url": "https://linkedin.com/in/new-lead-1", "first_name": "Batch Duplicate"},
        {"linkedin_url": "https://linkedin.com/in/new-lead-2", "first_name": "New 2"},
    ]

    res = await LeadImporter.ingest_leads(
        leads=leads_batch,
        campaign_id="camp_test",
        workspace_id="ws_test",
        db=mock_db,
        skip_already_contacted=False,
        skip_do_not_contact=True,
    )

    assert res["imported_count"] == 2  # new-lead-1 and new-lead-2
    assert res["duplicates_count"] == 2  # existing + batch duplicate
    assert res["skipped_count"] == 1  # vip-dnc


@pytest.mark.asyncio
async def test_leads_api_endpoints():
    """Verify CSV import and Do-Not-Contact API endpoints."""
    mock_db = Database(outreach_campaigns=[{"id": "camp_123", "workspace_id": "ws1", "name": "Test", "status": "draft"}])
    user = {"user_id": "u1", "default_workspace_id": "ws1"}

    csv_data = "First Name,LinkedIn\nSatya,https://linkedin.com/in/satyanadella"
    req = ImportCSVRequest(campaign_id="camp_123", csv_text=csv_data)

    res = await import_leads_csv(req=req, current_user=user, db=mock_db)
    assert res["imported_count"] == 1

    # Test DNC add
    dnc_req = DoNotContactRequest(linkedin_url="https://linkedin.com/in/vip-client", reason="Customer already")
    mock_db.outreach_do_not_contact.update_one = AsyncMock()
    dnc_res = await add_do_not_contact(req=dnc_req, current_user=user, db=mock_db)
    assert dnc_res["status"] == "success"
