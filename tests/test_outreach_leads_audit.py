"""Regression checks for the outreach Leads CRM flow."""
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest
import httpx
from fastapi import FastAPI, HTTPException

from api.deps import get_current_user
from db.mongo import get_db

from outreach.api.leads import (
    _lead_query,
    delete_lead,
    export_leads,
    import_leads_csv,
    update_lead_stage,
    ImportCSVRequest,
    UpdateLeadStageRequest,
    router,
)
from outreach.core.lead_importer import LeadImporter, normalize_linkedin_url


USER = {"user_id": "u1", "default_workspace_id": "ws1"}


def test_csv_handles_bom_empty_cells_and_host_variants():
    csv_text = "\ufeffLinkedIn URL,First Name,Company\nlinkedin.com/in/Alice,,\nwww.linkedin.com/in/Alice,Bob,Acme\n"
    parsed = LeadImporter.parse_csv_content(csv_text)
    assert len(parsed) == 2
    assert parsed[0]["first_name"] == ""
    assert parsed[0]["company_name"] == ""
    assert normalize_linkedin_url("linkedin.com/in/a?trk=x") == "https://linkedin.com/in/a"
    assert normalize_linkedin_url("linkedin.com/in/alice.smith") == "https://linkedin.com/in/alice.smith"
    assert normalize_linkedin_url("linkedin.com/in/a%0d") == ""


@pytest.mark.asyncio
async def test_import_always_excludes_dnc_and_deduplicates_hosts():
    db = SimpleNamespace()
    db.outreach_leads = SimpleNamespace(
        find=AsyncMock(return_value=[]), insert_many=AsyncMock(), count_documents=AsyncMock(return_value=0),
    )
    db.outreach_do_not_contact = SimpleNamespace(
        find=AsyncMock(return_value=[{"linkedin_url": "https://www.linkedin.com/in/blocked"}]),
    )
    db.outreach_campaigns = SimpleNamespace(update_one=AsyncMock())
    leads = [
        {"linkedin_url": "https://linkedin.com/in/blocked"},
        {"linkedin_url": "https://linkedin.com/in/alice"},
        {"linkedin_url": "https://www.linkedin.com/in/alice"},
    ]
    result = await LeadImporter.ingest_leads(
        leads, "camp1", "ws1", db, skip_already_contacted=False,
        skip_do_not_contact=False, campaign={"id": "camp1", "status": "draft"},
    )
    assert result == {"imported_count": 1, "skipped_count": 1, "duplicates_count": 1, "total_submitted": 3}
    inserted = db.outreach_leads.insert_many.await_args.args[0]
    assert inserted[0]["country_code"] == ""


@pytest.mark.asyncio
async def test_import_skips_only_recorded_prior_outreach():
    db = SimpleNamespace(
        outreach_leads=SimpleNamespace(
            find=AsyncMock(side_effect=[[], [{"linkedin_url": "https://www.linkedin.com/in/alice"}]]),
            insert_many=AsyncMock(),
        ),
        outreach_do_not_contact=SimpleNamespace(find=AsyncMock(return_value=[])),
        outreach_campaigns=SimpleNamespace(update_one=AsyncMock()),
    )
    result = await LeadImporter.ingest_leads(
        [{"linkedin_url": "https://linkedin.com/in/alice"}],
        "camp1", "ws1", db, campaign={"id": "camp1", "status": "draft"},
    )
    assert result["skipped_count"] == 1
    assert result["imported_count"] == 0
    assert db.outreach_leads.find.await_args_list[1].args[0]["last_action_at"] == {"$ne": None}


@pytest.mark.asyncio
async def test_query_escapes_search_and_scopes_campaign():
    db = SimpleNamespace(outreach_campaigns=SimpleNamespace(find_one=AsyncMock(return_value={"id": "camp1"})))
    query = await _lead_query("camp1", "queued", "unassigned", ".*", "US (East)", USER, db)
    assert query["$and"][1] == {"campaign_id": "camp1"}
    assert query["$and"][4]["$or"][0]["first_name"]["$regex"] == r"\.\*"
    assert query["$and"][5]["$or"][0]["location"]["$regex"] == r"US\ \(East\)"
    db.outreach_campaigns.find_one.return_value = None
    with pytest.raises(HTTPException) as exc:
        await _lead_query("other", None, None, None, None, USER, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_export_writes_filtered_rows_and_escapes_spreadsheet_formula():
    class Cursor:
        def __init__(self):
            self.docs = iter([
                {"first_name": "=HYPERLINK(\"https://bad.example\")", "linkedin_url": "https://linkedin.com/in/a"},
            ])

        def sort(self, _sort):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.docs)
            except StopIteration:
                raise StopAsyncIteration

    query_seen = []
    db = SimpleNamespace(outreach_leads=SimpleNamespace(find=lambda query: query_seen.append(query) or Cursor()))
    response = await export_leads(search="Alice", current_user=USER, db=db)
    content = "".join([chunk async for chunk in response.body_iterator])
    assert "first_name,last_name,linkedin_url" in content
    assert "'=HYPERLINK" in content
    assert "https://linkedin.com/in/a" in content
    assert query_seen[0]["$and"][1]["$or"][0]["first_name"]["$regex"] == "Alice"


@pytest.mark.asyncio
async def test_http_list_and_export_routes_share_filters():
    lead = {"id": "lead1", "first_name": "Alice", "linkedin_url": "https://linkedin.com/in/alice"}

    class Cursor:
        def sort(self, *_args):
            return self

        def skip(self, *_args):
            return self

        def limit(self, *_args):
            return self

        async def to_list(self, **_kwargs):
            return [dict(lead)]

        def __aiter__(self):
            self._remaining = [lead]
            return self

        async def __anext__(self):
            if self._remaining:
                return self._remaining.pop()
            raise StopAsyncIteration

    db = SimpleNamespace(outreach_leads=SimpleNamespace(
        find=lambda _query: Cursor(), count_documents=AsyncMock(return_value=1),
    ))
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/outreach")
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get("/api/v1/outreach/leads?search=Alice&limit=50")
        exported = await client.get("/api/v1/outreach/leads/export?search=Alice")
    assert listed.status_code == 200
    assert listed.json()["leads"][0]["id"] == "lead1"
    assert exported.status_code == 200
    assert "Alice" in exported.text


@pytest.mark.asyncio
async def test_stage_update_reports_missing_write():
    db = SimpleNamespace(outreach_leads=SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "lead1"}),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=0)),
    ))
    with pytest.raises(HTTPException) as exc:
        await update_lead_stage("lead1", UpdateLeadStageRequest(pipeline_stage="replied"), current_user=USER, db=db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_active_warmup_campaign_rejects_direct_import():
    db = SimpleNamespace(
        outreach_campaigns=SimpleNamespace(find_one=AsyncMock(return_value={"id": "camp1", "status": "active"})),
        outreach_engage_lists=SimpleNamespace(count_documents=AsyncMock(return_value=1)),
    )
    request = ImportCSVRequest(campaign_id="camp1", csv_text="LinkedIn URL\nhttps://linkedin.com/in/alice")
    with pytest.raises(HTTPException) as exc:
        await import_leads_csv(request, current_user=USER, db=db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_does_not_remove_in_flight_lead():
    db = SimpleNamespace(
        outreach_leads=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "lead1", "campaign_id": "camp1"}),
            delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=0)),
        ),
        outreach_campaigns=SimpleNamespace(find_one=AsyncMock(return_value={"status": "draft"})),
    )
    with pytest.raises(HTTPException) as exc:
        await delete_lead("lead1", current_user=USER, db=db)
    assert exc.value.status_code == 409
    assert db.outreach_leads.delete_one.await_args.args[0]["execution_claimed_at"] == {"$exists": False}
