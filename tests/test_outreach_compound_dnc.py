import pytest
from datetime import datetime, timezone
from outreach.core.lead_importer import (
    LeadImporter,
    build_lead_identifiers,
    check_compound_suppression,
    normalize_linkedin_url,
)
from outreach.models import LeadIdentifiers


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=None):
        return self.docs


class MockCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query=None, projection=None):
        query = query or {}
        results = []
        workspace_id = query.get("workspace_id")
        or_clauses = query.get("$or", [])

        for doc in self.docs:
            if workspace_id and doc.get("workspace_id") != workspace_id:
                continue
            if "last_action_at" in query and query["last_action_at"] == {"$ne": None} and not doc.get("last_action_at"):
                continue
            if "campaign_id" in query and doc.get("campaign_id") != query["campaign_id"]:
                continue

            if not or_clauses:
                results.append(doc)
                continue

            # Evaluate $or
            matched = False
            for clause in or_clauses:
                for k, v in clause.items():
                    target_val = None
                    if "." in k:
                        parts = k.split(".")
                        obj = doc
                        for p in parts:
                            obj = obj.get(p, {}) if isinstance(obj, dict) else None
                        target_val = obj
                    else:
                        target_val = doc.get(k)

                    if isinstance(v, dict) and "$in" in v:
                        in_list = v["$in"]
                        if target_val and target_val in in_list:
                            matched = True
                            break
                        # Case insensitive match for vanities/emails
                        if target_val and any(isinstance(target_val, str) and isinstance(x, str) and target_val.lower() == x.lower() for x in in_list):
                            matched = True
                            break
                    elif target_val == v:
                        matched = True
                        break
                if matched:
                    break

            if matched:
                results.append(doc)

        return MockCursor(results)

    async def find_one(self, query=None):
        cursor = self.find(query)
        docs = await cursor.to_list()
        return docs[0] if docs else None

    async def insert_many(self, docs):
        self.docs.extend(docs)

    async def update_one(self, filter_q, update_q, upsert=False):
        doc = await self.find_one(filter_q)
        if doc:
            if "$set" in update_q:
                doc.update(update_q["$set"])
        elif upsert:
            new_doc = dict(update_q.get("$set", {}))
            self.docs.append(new_doc)

    async def count_documents(self, filter_q):
        cursor = self.find(filter_q)
        docs = await cursor.to_list()
        return len(docs)


class MockDB:
    def __init__(self):
        self.outreach_leads = MockCollection()
        self.outreach_do_not_contact = MockCollection()
        self.outreach_campaigns = MockCollection()
        self.outreach_accounts = MockCollection()
        self.outreach_sequences = MockCollection()


@pytest.mark.asyncio
async def test_sales_nav_urn_suppresses_csv_import_by_vanity():
    db = MockDB()
    workspace_id = "ws-test-1"

    # Seed DNC with a Sales Navigator lead that has vanity and sales URN
    dnc_doc = {
        "workspace_id": workspace_id,
        "linkedin_url": "https://www.linkedin.com/sales/lead/ACwAA001122,NAME_SEARCH",
        "vanity_name": "alex-morgan",
        "sales_lead_urn": "ACwAA001122",
        "identifiers": {
            "normalized_url": None,
            "vanity_name": "alex-morgan",
            "member_urn": None,
            "sales_lead_urn": "ACwAA001122",
            "email": None,
        },
        "reason": "Requested DNC via Sales Nav export",
    }
    await db.outreach_do_not_contact.insert_many([dnc_doc])

    # Incoming CSV has a public profile URL: https://linkedin.com/in/alex-morgan
    csv_lead = {
        "raw_url": "https://linkedin.com/in/alex-morgan",
        "linkedin_url": "https://linkedin.com/in/alex-morgan",
        "first_name": "Alex",
        "last_name": "Morgan",
        "vanity_name": "alex-morgan",
    }

    preview = await LeadImporter.preview_leads(
        leads=[csv_lead],
        campaign_id="camp-1",
        workspace_id=workspace_id,
        db=db,
        skip_do_not_contact=True,
    )

    assert preview["valid_count"] == 0
    assert preview["dnc_count"] == 1
    assert preview["rows"][0]["rejection_code"] == "do_not_contact"
    assert "Do-Not-Contact" in preview["rows"][0]["error_reason"]


@pytest.mark.asyncio
async def test_email_suppression_across_different_urls():
    db = MockDB()
    workspace_id = "ws-test-2"

    # Seed DNC by email
    await db.outreach_do_not_contact.insert_many([{
        "workspace_id": workspace_id,
        "email": "sarah@acme.corp",
        "identifiers": {
            "normalized_url": None,
            "vanity_name": None,
            "member_urn": None,
            "sales_lead_urn": None,
            "email": "sarah@acme.corp",
        },
        "reason": "Unsubscribed via cold email",
    }])

    # Incoming CSV has different URL, but same email
    csv_lead = {
        "raw_url": "https://linkedin.com/in/sarah-connors-99",
        "linkedin_url": "https://linkedin.com/in/sarah-connors-99",
        "first_name": "Sarah",
        "last_name": "Connors",
        "email": "sarah@acme.corp",
    }

    preview = await LeadImporter.preview_leads(
        leads=[csv_lead],
        campaign_id="camp-1",
        workspace_id=workspace_id,
        db=db,
        skip_do_not_contact=True,
    )

    assert preview["valid_count"] == 0
    assert preview["dnc_count"] == 1
    assert preview["rows"][0]["rejection_code"] == "do_not_contact"


@pytest.mark.asyncio
async def test_batch_deduplication_across_compound_identifiers():
    db = MockDB()
    workspace_id = "ws-test-3"

    lead_1 = {
        "raw_url": "https://linkedin.com/in/johndoe",
        "linkedin_url": "https://linkedin.com/in/johndoe",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@doe.com",
    }
    lead_2 = {
        "raw_url": "https://www.linkedin.com/in/johndoe/",
        "linkedin_url": "https://www.linkedin.com/in/johndoe/",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@doe.com",
    }

    preview = await LeadImporter.preview_leads(
        leads=[lead_1, lead_2],
        campaign_id="camp-1",
        workspace_id=workspace_id,
        db=db,
    )

    assert preview["valid_count"] == 1
    assert preview["duplicate_count"] == 1
    assert preview["rows"][1]["rejection_code"] == "duplicate_batch"


@pytest.mark.asyncio
async def test_dual_name_storage_and_normalization():
    db = MockDB()
    workspace_id = "ws-test-4"
    campaign_id = "camp-1"

    raw_csv = """linkedin_url,first_name,last_name,company_name
https://linkedin.com/in/mcdonald-ceo,RONALD MCDONALD,CEO,FastFood Inc
https://linkedin.com/in/delacruz-invest,Elena de la Cruz,Partner,Venture Corp
https://linkedin.com/in/sarah-rocket,Sarah 🚀 | Founder,Smith,Tech Corp
"""
    parsed = LeadImporter.parse_csv_content(raw_csv)
    assert len(parsed) == 3

    # Verify parsed names
    assert parsed[0]["raw_first_name"] == "RONALD MCDONALD"
    assert parsed[0]["cleaned_first_name"] == "Ronald McDonald"

    assert parsed[1]["raw_first_name"] == "Elena de la Cruz"
    assert parsed[1]["cleaned_first_name"] == "Elena de la Cruz"  # Mixed case preserved!

    assert parsed[2]["raw_first_name"] == "Sarah 🚀 | Founder"
    assert parsed[2]["cleaned_first_name"] == "Sarah"  # Emojis & title noise stripped!

    # Ingest into campaign
    ingest_res = await LeadImporter.ingest_leads(
        leads=parsed,
        campaign_id=campaign_id,
        workspace_id=workspace_id,
        db=db,
    )
    assert ingest_res["imported_count"] == 3

    # Check database records
    leads_in_db = await db.outreach_leads.find({"campaign_id": campaign_id}).to_list()
    assert len(leads_in_db) == 3

    lead_0 = next(l for l in leads_in_db if "mcdonald-ceo" in l["linkedin_url"])
    assert lead_0["raw_first_name"] == "RONALD MCDONALD"
    assert lead_0["cleaned_first_name"] == "Ronald McDonald"
    assert lead_0["first_name"] == "Ronald McDonald"
    assert lead_0["identifiers"]["vanity_name"] == "mcdonald-ceo"
