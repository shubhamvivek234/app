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
    import_leads_urls,
    preview_leads_intake,
    update_lead_stage,
    ImportCSVRequest,
    ImportURLsRequest,
    LeadPreviewRequest,
    UpdateLeadStageRequest,
    router,
)
from outreach.core.lead_importer import LeadImporter, normalize_linkedin_url, extract_vanity_name


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


def test_parse_pasted_urls_variants():
    raw_text = (
        "https://www.linkedin.com/in/billgates, Bill Gates, Breakthrough Energy, Founder\n"
        "https://linkedin.com/in/satyanadella\tSatya\tNadella\tMicrosoft\n"
        "https://linkedin.com/in/sundarpichai Sundar Pichai\n"
        "https://linkedin.com/in/bare-profile\n"
        "https://invalid-domain.com/in/nobody\n"
    )
    parsed = LeadImporter.parse_pasted_urls(raw_text, default_first_name="Leader", default_company_name="Tech")
    assert len(parsed) == 5

    # Row 1: Bill Gates
    assert parsed[0]["linkedin_url"] == "https://www.linkedin.com/in/billgates"
    assert parsed[0]["vanity_name"] == "billgates"
    assert parsed[0]["first_name"] == "Bill"
    assert parsed[0]["last_name"] == "Gates"
    assert parsed[0]["company_name"] == "Breakthrough Energy"
    assert parsed[0]["job_title"] == "Founder"
    assert parsed[0]["source"] == "pasted_urls"

    # Row 2: Satya Nadella (tab-delimited)
    assert parsed[1]["linkedin_url"] == "https://linkedin.com/in/satyanadella"
    assert parsed[1]["vanity_name"] == "satyanadella"
    assert parsed[1]["first_name"] == "Satya"
    assert parsed[1]["last_name"] == "Nadella"
    assert parsed[1]["company_name"] == "Microsoft"

    # Row 3: Sundar Pichai (space-separated)
    assert parsed[2]["linkedin_url"] == "https://linkedin.com/in/sundarpichai"
    assert parsed[2]["first_name"] == "Sundar"
    assert parsed[2]["last_name"] == "Pichai"
    assert parsed[2]["company_name"] == "Tech"

    # Row 4: Bare profile falling back to user-supplied defaults
    assert parsed[3]["linkedin_url"] == "https://linkedin.com/in/bare-profile"
    assert parsed[3]["first_name"] == "Leader"
    assert parsed[3]["company_name"] == "Tech"

    # Row 5: Invalid domain
    assert parsed[4]["linkedin_url"] == ""
    assert parsed[4]["raw_url"] == "https://invalid-domain.com/in/nobody"


@pytest.mark.asyncio
async def test_preview_leads_row_level_errors_and_counts():
    db = SimpleNamespace(
        outreach_leads=SimpleNamespace(
            find=AsyncMock(side_effect=[
                # existing in campaign
                [{"linkedin_url": "https://linkedin.com/in/in-campaign"}],
                # contacted in workspace
                [{"linkedin_url": "https://linkedin.com/in/contacted-before"}],
            ]),
        ),
        outreach_do_not_contact=SimpleNamespace(
            find=AsyncMock(return_value=[{"linkedin_url": "https://linkedin.com/in/dnc-user"}]),
        ),
    )

    candidates = [
        {"linkedin_url": "https://linkedin.com/in/valid-lead", "first_name": "Valid", "last_name": "User"},
        {"linkedin_url": "https://linkedin.com/in/valid-lead", "first_name": "Valid", "last_name": "User"}, # dupe in batch
        {"linkedin_url": "https://linkedin.com/in/in-campaign", "first_name": "Camp", "last_name": "User"}, # dupe in campaign
        {"linkedin_url": "https://linkedin.com/in/contacted-before", "first_name": "Prior", "last_name": "User"}, # contacted
        {"linkedin_url": "https://linkedin.com/in/dnc-user", "first_name": "Blocked", "last_name": "User"}, # dnc
        {"raw_url": "https://not-linkedin.com/bad", "linkedin_url": "", "first_name": "Bad", "last_name": "URL"}, # invalid url
        {"linkedin_url": "https://linkedin.com/in/no-name", "first_name": "", "last_name": ""}, # missing name
    ]

    preview = await LeadImporter.preview_leads(
        leads=candidates,
        campaign_id="camp1",
        workspace_id="ws1",
        db=db,
        skip_already_contacted=True,
        skip_do_not_contact=True,
        require_name=True,
    )

    assert preview["total_submitted"] == 7
    assert preview["valid_count"] == 1
    assert preview["duplicate_count"] == 2  # 1 batch dupe + 1 campaign dupe
    assert preview["contacted_count"] == 1
    assert preview["dnc_count"] == 1
    assert preview["invalid_count"] == 2  # 1 invalid url + 1 missing name

    rows = preview["rows"]
    assert rows[0]["status"] == "valid"
    assert rows[1]["rejection_code"] == "duplicate_batch"
    assert rows[2]["rejection_code"] == "duplicate_campaign"
    assert rows[3]["rejection_code"] == "duplicate_contacted"
    assert rows[4]["rejection_code"] == "do_not_contact"
    assert rows[5]["rejection_code"] == "invalid_url"
    assert "Invalid LinkedIn profile URL" in rows[5]["error_reason"]
    assert rows[6]["rejection_code"] == "missing_name"
    assert "First name is required" in rows[6]["error_reason"]


@pytest.mark.asyncio
async def test_http_preview_and_import_urls():
    db = SimpleNamespace(
        outreach_campaigns=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "camp1", "status": "draft"}),
            update_one=AsyncMock(),
        ),
        outreach_leads=SimpleNamespace(
            find=AsyncMock(return_value=[]),
            insert_many=AsyncMock(),
            count_documents=AsyncMock(return_value=0),
        ),
        outreach_do_not_contact=SimpleNamespace(find=AsyncMock(return_value=[])),
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/outreach")
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db] = lambda: db

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Test preview endpoint
        preview_res = await client.post("/api/v1/outreach/leads/preview", json={
            "campaign_id": "camp1",
            "source_type": "pasted_urls",
            "raw_text": "https://linkedin.com/in/alex, Alex, Smith\nhttps://linkedin.com/in/alex, Alex, Smith",
            "require_name": True,
        })
        assert preview_res.status_code == 200
        preview_data = preview_res.json()
        assert preview_data["total_submitted"] == 2
        assert preview_data["valid_count"] == 1
        assert preview_data["duplicate_count"] == 1

        # 2. Test import-urls endpoint
        import_res = await client.post("/api/v1/outreach/leads/import-urls", json={
            "campaign_id": "camp1",
            "urls_text": "https://linkedin.com/in/alex, Alex, Smith",
            "require_name": True,
            "consent_basis": "user_provided",
        })
        assert import_res.status_code == 200
        import_data = import_res.json()
        assert import_data["imported_count"] == 1
        assert import_data["duplicates_count"] == 0

        # Verify inserted lead has source and source_metadata
        inserted = db.outreach_leads.insert_many.await_args.args[0]
        assert inserted[0]["source"] == "pasted_urls"
        assert inserted[0]["source_metadata"]["consent_basis"] == "user_provided"
        assert inserted[0]["first_name"] == "Alex"


@pytest.mark.asyncio
async def test_lead_activity_and_notes():
    now_iso = "2026-09-30T10:00:00Z"
    lead_doc = {
        "id": "lead_act_1",
        "workspace_id": "ws1",
        "user_id": "u1",
        "campaign_id": "camp_act_1",
        "assigned_account_id": "acc_1",
        "linkedin_url": "https://www.linkedin.com/in/activity-target",
        "first_name": "Active",
        "last_name": "Lead",
        "execution_state": "in_progress",
        "pipeline_stage": "in_campaign",
        "current_node_id": "node_followup_1",
        "next_action_due_at": now_iso,
        "source": "pasted_urls",
        "created_at": "2026-09-29T10:00:00Z",
    }

    inserted_notes = []

    class MockNotesCol:
        async def find(self, query=None, *args, **kwargs):
            return [
                {
                    "id": "note_1",
                    "lead_id": "lead_act_1",
                    "workspace_id": "ws1",
                    "note": "Initial qualification call scheduled",
                    "author": "Alice",
                    "created_at": "2026-09-29T12:00:00Z",
                }
            ]

        async def insert_one(self, doc):
            inserted_notes.append(doc)
            return True

    class MockTasksCol:
        async def find(self, query=None, *args, **kwargs):
            return [
                {
                    "id": "task_1",
                    "task_type": "send_invite",
                    "status": "completed",
                    "node_id": "node_invite",
                    "attempt_id": "att_1",
                    "resolved_at": "2026-09-29T11:00:00Z",
                }
            ]

    class MockThreadsCol:
        async def find_one(self, query=None, *args, **kwargs):
            return {
                "lead_id": "lead_act_1",
                "workspace_id": "ws1",
                "messages": [
                    {
                        "id": "msg_1",
                        "sender_type": "lead",
                        "sender_name": "Active Lead",
                        "body": "Sounds interesting, let's chat!",
                        "timestamp": "2026-09-29T14:00:00Z",
                    }
                ],
            }

    db = SimpleNamespace(
        outreach_leads=SimpleNamespace(
            find_one=AsyncMock(return_value=lead_doc),
        ),
        outreach_accounts=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "acc_1", "account_name": "Sarah Connor"}),
        ),
        outreach_campaigns=SimpleNamespace(
            find_one=AsyncMock(return_value={"id": "camp_act_1", "name": "Enterprise Outreach"}),
        ),
        outreach_tasks=MockTasksCol(),
        outreach_inbox_threads=MockThreadsCol(),
        outreach_lead_notes=MockNotesCol(),
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/outreach")
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db] = lambda: db

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. GET /activity
        res = await client.get("/api/v1/outreach/leads/lead_act_1/activity")
        assert res.status_code == 200
        data = res.json()
        assert data["lead"]["id"] == "lead_act_1"
        assert data["lead"]["assigned_sender_name"] == "Sarah Connor"
        assert data["lead"]["campaign_name"] == "Enterprise Outreach"
        assert data["lead"]["current_node_id"] == "node_followup_1"
        assert data["total_activities"] >= 3  # task, message, note, lifecycle
        kinds = [a["kind"] for a in data["activities"]]
        assert "task" in kinds
        assert "message" in kinds
        assert "note" in kinds
        assert "lifecycle" in kinds

        # 2. POST /notes
        note_res = await client.post(
            "/api/v1/outreach/leads/lead_act_1/notes",
            json={"note": "Lead replied via email asking for slide deck."},
        )
        assert note_res.status_code == 200
        assert len(inserted_notes) == 1
        assert inserted_notes[0]["note"] == "Lead replied via email asking for slide deck."


@pytest.mark.asyncio
async def test_lead_pause_and_resume_preflight():
    lead_doc = {
        "id": "lead_ctrl_1",
        "workspace_id": "ws1",
        "user_id": "u1",
        "linkedin_url": "https://www.linkedin.com/in/controllable",
        "execution_state": "queued",
        "assigned_account_id": "acc_sender_1",
    }

    db_leads = SimpleNamespace(
        find_one=AsyncMock(return_value=dict(lead_doc)),
        update_one=AsyncMock(),
    )
    db_tasks = SimpleNamespace(
        update_many=AsyncMock(),
        count_documents=AsyncMock(return_value=0),
    )
    db_dnc = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
    )
    db_accounts = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "acc_sender_1", "status": "active"}),
    )

    db = SimpleNamespace(
        outreach_leads=db_leads,
        outreach_tasks=db_tasks,
        outreach_do_not_contact=db_dnc,
        outreach_accounts=db_accounts,
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/outreach")
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db] = lambda: db

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Pause lead
        pause_res = await client.post(
            "/api/v1/outreach/leads/lead_ctrl_1/pause",
            json={"reason": "Manual operator pause before demo"},
        )
        assert pause_res.status_code == 200
        assert pause_res.json()["status"] == "paused"
        assert pause_res.json()["pause_reason"] == "Manual operator pause before demo"
        assert db_tasks.update_many.await_count == 1

        # 2. Resume lead - DNC blocks
        db_dnc.find_one.return_value = {"linkedin_url": "https://www.linkedin.com/in/controllable"}
        resume_dnc_res = await client.post("/api/v1/outreach/leads/lead_ctrl_1/resume")
        assert resume_dnc_res.status_code == 409
        assert "exclusion list" in resume_dnc_res.json()["detail"]
        db_dnc.find_one.return_value = None

        # 3. Resume lead - Uncertain task blocks
        db_tasks.count_documents.return_value = 1
        resume_unc_res = await client.post("/api/v1/outreach/leads/lead_ctrl_1/resume")
        assert resume_unc_res.status_code == 409
        assert "uncertain outcome" in resume_unc_res.json()["detail"]
        db_tasks.count_documents.return_value = 0

        # 4. Resume lead - Inactive sender blocks
        db_accounts.find_one.return_value = None
        resume_acc_res = await client.post("/api/v1/outreach/leads/lead_ctrl_1/resume")
        assert resume_acc_res.status_code == 409
        assert "inactive or disconnected" in resume_acc_res.json()["detail"]
        db_accounts.find_one.return_value = {"id": "acc_sender_1", "status": "active"}

        # 5. Clean resume passes
        resume_ok_res = await client.post("/api/v1/outreach/leads/lead_ctrl_1/resume")
        assert resume_ok_res.status_code == 200
        assert resume_ok_res.json()["status"] == "resumed"
        assert resume_ok_res.json()["execution_state"] == "queued"


