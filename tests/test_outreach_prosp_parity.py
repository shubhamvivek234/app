"""
Prosp AI Parity Test Suite:
Tests Lead Finder, Post Engagers Ingestion, Pipeline Stage Updating,
Inbox Reminders/Snippets/Tags, AI Prompt Library & Preview, and Outreach Analytics.
"""
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock
from cryptography.fernet import Fernet

if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from fastapi import HTTPException
from tests.outreach_memory import matches

from outreach.api.leads import (
    LeadFinderPreviewRequest,
    LeadFinderEnrollRequest,
    ImportPostEngagersRequest,
    UpdateLeadStageRequest,
    preview_lead_finder,
    enroll_finder_leads,
    import_post_engagers,
    update_lead_stage,
    list_leads,
)
from outreach.api.inbox import (
    CreateReminderRequest,
    CreateSnippetRequest,
    CreateTagRequest,
    ToggleTagRequest,
    create_thread_reminder,
    list_thread_reminders,
    delete_thread_reminder,
    list_snippets,
    create_snippet,
    delete_snippet,
    list_tags,
    create_tag,
    delete_tag,
    toggle_thread_tag,
)
from outreach.api.prompts import (
    CreateAIPromptRequest,
    PromptPreviewRequest,
    list_prompts,
    create_prompt,
    delete_prompt,
    preview_evaluated_message,
)
from outreach.api.analytics import get_outreach_analytics, live_activity_feed


class MockCursor:
    def __init__(self, items):
        self.items = list(items)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, n):
        idx = int(getattr(n, "default", n))
        self.items = self.items[idx:]
        return self

    def limit(self, n):
        idx = int(getattr(n, "default", n))
        self.items = self.items[:idx]
        return self

    async def to_list(self, length=None):
        if length is not None:
            return list(self.items[:length])
        return list(self.items)

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class MockCollection:
    def __init__(self, items=None):
        self.items = list(items or [])

    def find(self, query=None, *args, **kwargs):
        return MockCursor([dict(item) for item in self.items if matches(item, query or {})])

    async def find_one(self, query=None, *args, **kwargs):
        for item in self.items:
            if matches(item, query or {}):
                return dict(item)
        return None

    async def insert_one(self, doc):
        self.items.append(dict(doc))
        return AsyncMock(inserted_id="mock_id")

    async def insert_many(self, docs):
        self.items.extend([dict(d) for d in docs])
        return AsyncMock(inserted_ids=["mock_id" for _ in docs])

    async def update_one(self, query, update, upsert=False):
        for item in self.items:
            if matches(item, query or {}):
                if "$set" in update:
                    item.update(update["$set"])
                if "$unset" in update:
                    for un_k in update["$unset"]:
                        item.pop(un_k, None)
                return AsyncMock(modified_count=1, matched_count=1)
        if upsert:
            new_item = dict(query)
            if "$set" in update:
                new_item.update(update["$set"])
            self.items.append(new_item)
            return AsyncMock(upserted_id="mock_upserted_id")
        return AsyncMock(modified_count=0, matched_count=0)

    async def delete_one(self, query):
        for i, item in enumerate(self.items):
            if matches(item, query or {}):
                self.items.pop(i)
                return AsyncMock(deleted_count=1)
        return AsyncMock(deleted_count=0)

    async def count_documents(self, query=None):
        return sum(1 for item in self.items if matches(item, query or {}))


class MockDatabase:
    def __init__(self):
        self.outreach_leads = MockCollection()
        self.outreach_campaigns = MockCollection()
        self.outreach_inbox_threads = MockCollection()
        self.outreach_inbox_reminders = MockCollection()
        self.outreach_inbox_snippets = MockCollection()
        self.outreach_inbox_tags = MockCollection()
        self.outreach_ai_prompts = MockCollection()
        self.outreach_tasks = MockCollection()
        self.outreach_email_operations = MockCollection()
        self.outreach_email_inbound_events = MockCollection()
        self.outreach_do_not_contact = MockCollection()
        self.outreach_event_outbox = MockCollection()
        self.outreach_workspace_erasure = MockCollection()
        self.outreach_import_reports = MockCollection()


USER = {"user_id": "usr_test_1", "default_workspace_id": "ws_test_1", "name": "Growth Pro"}


# ── 1. Lead Finder & Post Engagers Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_preview_lead_finder():
    req = LeadFinderPreviewRequest(
        title="VP of Growth",
        industry="SaaS & Enterprise Software",
        location="San Francisco, CA",
        connection_degree="2nd",
        has_posted_recently=True,
        limit=5,
    )
    db = MockDatabase()
    db.outreach_sequences = MockCollection()
    with pytest.raises(HTTPException) as exc:
        await preview_lead_finder(req, current_user=USER, db=db)
    assert exc.value.status_code == 501
    assert db.outreach_leads.items == []


@pytest.mark.asyncio
async def test_enroll_finder_leads():
    db = MockDatabase()
    db.outreach_sequences = MockCollection()
    db.outreach_campaigns.items.append({"id": "cmp_1", "workspace_id": "ws_test_1", "status": "draft", "name": "Test Campaign", "leads_count": 0})

    leads = [
        {"linkedin_url": "https://linkedin.com/in/lead-1", "first_name": "L1", "last_name": "One"},
        {"linkedin_url": "https://linkedin.com/in/lead-2", "first_name": "L2", "last_name": "Two"},
    ]
    req = LeadFinderEnrollRequest(campaign_id="cmp_1", leads=leads)
    with pytest.raises(HTTPException) as exc:
        await enroll_finder_leads(req, current_user=USER, db=db)
    assert exc.value.status_code == 501
    assert db.outreach_leads.items == []


@pytest.mark.asyncio
async def test_import_post_engagers():
    db = MockDatabase()
    db.outreach_sequences = MockCollection()
    db.outreach_campaigns.items.append({"id": "cmp_1", "workspace_id": "ws_test_1", "status": "draft", "name": "Engager Campaign", "leads_count": 0})

    req = ImportPostEngagersRequest(
        campaign_id="cmp_1",
        post_url="https://www.linkedin.com/posts/satyanadella_ai-advances-activity-12345",
        push_option="Only existing comments/likes",
        export_likes=True,
        export_comments=True,
        max_leads=8,
    )
    with pytest.raises(HTTPException) as exc:
        await import_post_engagers(req, current_user=USER, db=db)
    assert exc.value.status_code == 501
    assert db.outreach_leads.items == []


@pytest.mark.asyncio
async def test_update_lead_stage_and_filtering():
    db = MockDatabase()
    db.outreach_sequences = MockCollection()
    lead_doc = {
        "id": "lead_stage_1",
        "workspace_id": "ws_test_1",
        "first_name": "Alex",
        "last_name": "Tester",
        "pipeline_stage": "unassigned",
    }
    db.outreach_leads.items.append(lead_doc)

    # Update stage to 'call_booked'
    req = UpdateLeadStageRequest(pipeline_stage="call_booked")
    res = await update_lead_stage("lead_stage_1", req, current_user=USER, db=db)

    assert res["status"] == "updated"
    assert res["pipeline_stage"] == "call_booked"
    assert lead_doc["pipeline_stage"] == "call_booked"

    # Filter with pipeline_stage
    list_res = await list_leads(pipeline_stage="call_booked", skip=0, limit=50, current_user=USER, db=db)
    assert list_res["total"] == 1


# ── 2. Inbox Reminders, Snippets & Tags Tests ──────────────────────────────

@pytest.mark.asyncio
async def test_inbox_reminders():
    db = MockDatabase()
    db.outreach_sequences = MockCollection()
    thread_doc = {"id": "th_1", "user_id": USER["user_id"], "workspace_id": USER["default_workspace_id"]}
    db.outreach_inbox_threads.items.append(thread_doc)

    rem_time = datetime.now(timezone.utc) + timedelta(days=1)
    req = CreateReminderRequest(remind_at=rem_time, note="Follow up on pitch deck")

    # Set reminder
    res = await create_thread_reminder("th_1", req, current_user=USER, db=db)
    assert res["status"] == "created"
    assert res["reminder"]["note"] == "Follow up on pitch deck"
    assert thread_doc["reminder_note"] == "Follow up on pitch deck"

    # List reminders
    rems = await list_thread_reminders("th_1", current_user=USER, db=db)
    assert len(rems) == 1

    # Delete reminder
    del_res = await delete_thread_reminder(res["reminder"]["id"], current_user=USER, db=db)
    assert del_res["status"] == "deleted"


@pytest.mark.asyncio
async def test_inbox_snippets():
    db = MockDatabase()
    db.outreach_sequences = MockCollection()

    # 1. Listing seeds default snippets if empty
    snips = await list_snippets(current_user=USER, db=db)
    assert len(snips) >= 3
    titles = [s["title"] for s in snips]
    assert "Calendar link" in titles
    assert "Pricing list" in titles

    # 2. Create custom snippet
    new_req = CreateSnippetRequest(
        title="Demo Link",
        body="Here is our 2-min interactive tour: https://unravler.com/demo",
        shortcut="demo",
    )
    created = await create_snippet(new_req, current_user=USER, db=db)
    assert created["title"] == "Demo Link"

    # 3. Delete snippet
    del_res = await delete_snippet(created["id"], current_user=USER, db=db)
    assert del_res["status"] == "deleted"


@pytest.mark.asyncio
async def test_inbox_tags():
    from tests.outreach_memory import Database
    db = Database(outreach_inbox_threads=[{"id": "th_tag_1", "workspace_id": USER["default_workspace_id"],
        "lead_id": "lead-tag", "tags": ["Hot lead"]}], outreach_leads=[
        {"id": "lead-tag", "workspace_id": USER["default_workspace_id"]}])
    assert await list_tags(current_user=USER, db=db) == []
    created = await create_tag(CreateTagRequest(name="Enterprise VIP", color="#10b981"), current_user=USER, db=db)
    result = await toggle_thread_tag("th_tag_1", ToggleTagRequest(tag_id=created["id"], operation="add", revision=0), current_user=USER, db=db)
    assert [tag["name"] for tag in result["tags"]] == ["Enterprise VIP"]
    assert result["legacy_tags"] == ["Hot lead"]
    result = await toggle_thread_tag("th_tag_1", ToggleTagRequest(tag_id=created["id"], operation="remove", revision=1), current_user=USER, db=db)
    assert result["tags"] == []
    assert db.outreach_inbox_threads.docs[0]["tags"] == ["Hot lead"]


# ── 3. AI Prompts Library & Message Preview Tests ──────────────────────────

@pytest.mark.asyncio
async def test_prompts_library_and_preview():
    db = MockDatabase()
    db.outreach_sequences = MockCollection()

    # 1. Listing includes server-owned curated guidance without database seeding
    prompts = await list_prompts(current_user=USER, db=db)
    assert len(prompts) >= 5
    prompt_names = [p["name"] for p in prompts]
    assert "Saw you're doing X (3-5 words)" in prompt_names
    assert "Website designer personalised first line" in prompt_names

    # 2. Create custom prompt
    req = CreateAIPromptRequest(
        name="Conference Speaker Opener",
        prompt_text="Congratulate them on their recent keynote speech at SaaStr.",
        description="Speaker invite hook",
        author_name="Sales Team",
    )
    created = await create_prompt(req, current_user=USER, db=db)
    assert created["name"] == "Conference Speaker Opener"

    # 3. Evaluate preview with both variable {{first_name}} and AI token ✨ [Saw you're doing X (3-5 words)]
    prev_req = PromptPreviewRequest(
        template="Hey {{first_name}}, saw that you're ✨ [Saw you're doing X (3-5 words)]. Let's chat!",
        custom_lead_data={"first_name": "Jordan", "company_name": "Supabase", "headline": "Founder at Supabase | Enhancing customer connection with AI"},
    )
    prev_res = await preview_evaluated_message(prev_req, current_user=USER, db=db)
    assert "Hey Jordan" in prev_res["evaluated_text"]
    assert "[Prompt guidance not generated:" in prev_res["evaluated_text"]
    assert prev_res["has_ai_tokens"] is True
    assert "enhancing customer connection with AI" in prev_res["ai_generated_text"]

    # 4. Evaluate preview with evaluate_ai=True resolves AI prompt dynamically and increments custom prompt runs_count
    ai_req = PromptPreviewRequest(
        template="Hey {{first_name}}, saw that you're ✨ [Saw you're doing X (3-5 words)]. ✨ [Conference Speaker Opener]",
        custom_lead_data={"first_name": "Son", "company_name": "Prosp", "headline": "CEO | Enhancing customer connection with AI"},
        evaluate_ai=True,
    )
    ai_res = await preview_evaluated_message(ai_req, current_user=USER, db=db)
    assert "Hey Son, saw that you're enhancing customer connection with AI." in ai_res["evaluated_text"]
    assert "[Prompt guidance not generated:" not in ai_res["evaluated_text"]
    assert ai_res["sender_preview"]["avatar"] == ""


# ── 4. Outreach Analytics Dashboard Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_outreach_analytics():
    db = MockDatabase()
    db.outreach_sequences = MockCollection()
    res = await get_outreach_analytics(campaign_id="all", timeframe="14d", current_user=USER, db=db)

    assert "kpis" in res
    assert "requests" in res["kpis"]
    assert "messages" in res["kpis"]
    assert "engagement" in res["kpis"]
    assert "email" in res["kpis"]
    assert "daily_chart" in res
    assert len(res["daily_chart"]) == 14
    assert res["daily_chart"][0]["sent"] >= 0
    assert res["daily_chart"][0]["accepted"] >= 0
    assert "benchmarks" in res
    assert "recommendations" in res
    assert isinstance(res["recommendations"], list)

    # Verify 90d timeframe support
    res_90 = await get_outreach_analytics(campaign_id="all", timeframe="90d", current_user=USER, db=db)
    assert len(res_90["daily_chart"]) == 90
    assert res_90["timeframe"] == "90d"


@pytest.mark.asyncio
async def test_outreach_analytics_live_feed():
    db = MockDatabase()
    db.outreach_sequences = MockCollection()
    res = await live_activity_feed(current_user=USER, db=db)
    assert res.media_type == "text/event-stream"
    assert res.headers["Cache-Control"] == "no-cache"
    assert res.headers["Connection"] == "keep-alive"


@pytest.mark.asyncio
async def test_import_receipt_recovery_and_source_filtering():
    from outreach.api.leads import ImportURLsRequest, import_leads_urls, get_import_receipt
    db = MockDatabase()
    db.outreach_sequences = MockCollection()
    db.outreach_import_reports = MockCollection()
    db.outreach_campaigns.items.append({
        "_id": "native_cmp_1",
        "id": "cmp_1",
        "workspace_id": "ws_test_1",
        "status": "draft",
        "name": "Test Campaign",
        "leads_count": 0,
    })

    req = ImportURLsRequest(
        campaign_id="cmp_1",
        urls_text="https://linkedin.com/in/alex-one, Alex One",
        request_id="req_test_recover_123",
    )
    first = await import_leads_urls(req, current_user=USER, db=db, import_scope=None)
    assert first["imported_count"] == 1
    assert len(db.outreach_leads.items) == 1

    # Retrying with the same request_id returns the recovered receipt without duplicating leads
    second = await import_leads_urls(req, current_user=USER, db=db, import_scope=None)
    assert second["recovered"] is True
    assert second["imported_count"] == 1
    assert len(db.outreach_leads.items) == 1

    # Direct receipt lookup by request_id
    recovered = await get_import_receipt("req_test_recover_123", campaign_id="cmp_1", current_user=USER, db=db, import_scope=None)
    assert recovered["recovered"] is True
    assert recovered["imported_count"] == 1

    # Filter leads by source
    filtered = await list_leads(source="pasted_urls", skip=0, limit=50, current_user=USER, db=db)
    assert filtered["total"] == 1


@pytest.mark.asyncio
async def test_sender_readiness_and_effective_allowance():
    from outreach.api.accounts import list_outreach_accounts
    db = MockDatabase()
    db.outreach_sequences = MockCollection()
    db.outreach_accounts = MockCollection([
        {
            "id": "acc_ready_1",
            "workspace_id": "ws_test_1",
            "account_name": "Alex Sender",
            "status": "active",
            "session_cookie_enc": "gAAAAAB_dummy",
            "proxy": {"host": "isp.proxy.example", "port": 8080},
            "warmup_level": 4,
            "limits": {"connection_invites": 30, "messages": 25},
            "daily_counters": {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "connection_invites": 25,
                "messages": 5,
            },
            "weekly_invites_sent": 40,
        }
    ])
    accounts = await list_outreach_accounts(current_user=USER, db=db)
    assert len(accounts) == 1
    readiness = accounts[0]["readiness"]
    assert readiness["can_work_now"] is True
    assert readiness["blockers"] == []
    inv_allow = readiness["effective_allowance"]["connection_invites"]
    assert inv_allow["saved_cap"] == 30
    assert inv_allow["used_today"] == 25
    assert inv_allow["remaining_today"] == 5
    assert readiness["effective_allowance"]["weekly_invites_remaining"] == 60


@pytest.mark.asyncio
async def test_sequence_migration_preview_and_live_edit_continuity():
    from outreach.api.sequences import (
        LiveEditSequenceRequest,
        preview_campaign_sequence_migration,
        live_edit_campaign_sequence,
    )
    db = MockDatabase()
    db.outreach_sequences = MockCollection()
    db.outreach_sequences = MockCollection([
        {
            "workspace_id": "ws_test_1",
            "campaign_id": "cmp_mig_1",
            "version": 1,
            "compiled_dag": {
                "root_node_ids": ["step_1"],
                "nodes": {
                    "step_1": {"id": "step_1", "type": "connection_request", "next_default": "step_2"},
                    "step_2": {"id": "step_2", "type": "send_message", "next_default": None},
                },
            },
        }
    ])
    db.outreach_sequence_versions = MockCollection()
    db.outreach_campaigns.items.append({
        "id": "cmp_mig_1",
        "workspace_id": "ws_test_1",
        "status": "paused",
        "authorization_revision": 1,
        "sender_account_ids": ["sender_new"],
    })
    wait_ts = datetime.now(timezone.utc) - timedelta(hours=12)
    db.outreach_leads.items.append({
        "id": "lead_wait_1",
        "workspace_id": "ws_test_1",
        "campaign_id": "cmp_mig_1",
        "first_name": "Sam",
        "current_node_id": "step_1",
        "assigned_account_id": "sender_old",
        "execution_state": "waiting_trigger",
        "waiting_for_connection_at": wait_ts,
        "sequence_version": 1,
    })

    req_unmapped = LiveEditSequenceRequest(
        campaign_id="cmp_mig_1",
        nodes=[
            {"id": "step_1_new", "type": "connection_request", "delay_hours": 0, "config": {"note": ""}},
            {"id": "step_2", "type": "send_message", "delay_hours": 24, "config": {"body": "Hi"}},
        ],
        edges=[{"id": "e1", "source": "step_1_new", "target": "step_2", "label": "accepted"}],
    )
    preview = await preview_campaign_sequence_migration(req_unmapped, current_user=USER, db=db)
    assert preview["can_migrate_safely"] is False
    assert len(preview["needs_node_mapping"]) == 1
    assert len(preview["needs_sender_mapping"]) == 1

    req_mapped = LiveEditSequenceRequest(
        campaign_id="cmp_mig_1",
        nodes=req_unmapped.nodes,
        edges=req_unmapped.edges,
        node_mapping={"step_1": "step_1_new"},
        sender_mapping={"sender_old": "sender_new"},
    )
    preview_ok = await preview_campaign_sequence_migration(req_mapped, current_user=USER, db=db)
    assert preview_ok["can_migrate_safely"] is True
    assert preview_ok["preserved_waiting_count"] == 1
    assert preview_ok["mapped_nodes_count"] == 1
    assert preview_ok["mapped_senders_count"] == 1


@pytest.mark.asyncio
async def test_dripify_videos_6_to_12_parity():
    from outreach.core.search_sources import classify_linkedin_source_url
    from outreach.core.lead_importer import LeadImporter, normalize_any_linkedin_profile_url
    from outreach.core.dag_compiler import interpolate_template
    from outreach.api.prompts import PromptPreviewRequest, preview_evaluated_message
    from outreach.api.leads import pause_lead, resume_lead
    from outreach.api.campaigns import get_campaign

    # Video #6: LinkedIn Event Attendees source classification
    ev_search = classify_linkedin_source_url("https://www.linkedin.com/search/results/people/?eventAttending=%5B%2271928374%22%5D")
    assert ev_search["is_valid"] is True
    assert ev_search["source_type"] == "events"
    assert ev_search["max_profiles"] == 1000
    assert ev_search["requires_event_attendance"] is True
    assert len(ev_search["event_batches"]) >= 3

    ev_page = classify_linkedin_source_url("https://www.linkedin.com/events/71928374/comments/")
    assert ev_page["is_valid"] is True
    assert ev_page["source_type"] == "events"

    # Video #7: Pasting Standard (/in/), Sales Navigator (/sales/lead/), and Recruiter (/talent/profile/) URLs
    assert normalize_any_linkedin_profile_url("https://www.linkedin.com/sales/lead/ACwAAB12345,NAME_SEARCH") == "https://www.linkedin.com/sales/lead/ACwAAB12345"
    assert normalize_any_linkedin_profile_url("https://www.linkedin.com/talent/profile/ACwAAC67890?trk=recruiter") == "https://www.linkedin.com/talent/profile/ACwAAC67890"
    assert normalize_any_linkedin_profile_url("https://www.linkedin.com/talent/hire/999/profile/ACwAAD11111") == "https://www.linkedin.com/talent/profile/ACwAAD11111"

    pasted = LeadImporter.parse_pasted_urls(
        "https://www.linkedin.com/in/alice-smith, Alice, Smith, Acme\n"
        "https://www.linkedin.com/sales/lead/ACwAAB12345, Bob, Jones, Beta\n"
        "https://www.linkedin.com/talent/profile/ACwAAC67890, Carol, Lee, Gamma\n"
        "https://www.linkedin.com/sales/lead/ACwAAB12345, BobDupe, Jones, Beta"
    )
    assert len(pasted) == 4
    db = MockDatabase()
    db.outreach_sequences = MockCollection()
    prev = await LeadImporter.preview_leads(pasted, "cmp_1", "ws_test_1", db, require_name=True)
    assert prev["valid_count"] == 3
    assert prev["duplicate_count"] == 1
    assert prev["rows"][3]["rejection_code"] == "duplicate_batch"

    # Video #12: 15+ Personalization Variables ({{university_name}}, {{profile_type}}, {{location}}) & InMail Subject Line
    rendered = interpolate_template(
        "Hi {{first_name}} ({{profile_type}}) from {{university_name}} in {{location}}",
        {"first_name": "Elena", "school": "MIT", "location": "Boston, MA", "is_open_profile": True},
    )
    assert rendered == "Hi Elena (Open Profile) from MIT in Boston, MA"

    inmail_prev = await preview_evaluated_message(
        PromptPreviewRequest(
            template="Hi {{first_name}}, fellow {{university_name}} alum here!",
            subject="Quick note for {{first_name}} at {{company_name}} ({{profile_type}})",
            custom_lead_data={
                "first_name": "Marcus",
                "company_name": "ScaleOps",
                "university_name": "Stanford University",
                "profile_type": "Open Profile",
            },
        ),
        current_user=USER,
        db=db,
    )
    assert inmail_prev["evaluated_subject"] == "Quick note for Marcus at ScaleOps (Open Profile)"
    assert "Stanford University" in inmail_prev["evaluated_text"]

    # Video #8, #9, #10, #11: Lead Pause/Resume Sequence, 5-Stage Funnel Breakdown, Per-List Performance & Account Stats
    db.outreach_campaigns.items.append({
        "id": "cmp_funnel_1",
        "workspace_id": "ws_test_1",
        "name": "Q4 Outbound",
        "status": "active",
        "sender_account_ids": [],
    })
    db.outreach_leads.items.extend([
        {
            "_id": "l1",
            "id": "lead_f1",
            "workspace_id": "ws_test_1",
            "campaign_id": "cmp_funnel_1",
            "first_name": "Alice",
            "last_name": "Smith",
            "linkedin_url": "https://www.linkedin.com/in/alice-smith",
            "execution_state": "queued",
            "source_metadata": {"list_name": "SaaS Founders US"},
        },
        {
            "_id": "l2",
            "id": "lead_f2",
            "workspace_id": "ws_test_1",
            "campaign_id": "cmp_funnel_1",
            "first_name": "Bob",
            "last_name": "Jones",
            "linkedin_url": "https://www.linkedin.com/in/bob-jones",
            "execution_state": "invited",
            "is_connected": False,
            "source_metadata": {"list_name": "Event Attendees NYC"},
        },
    ])
    paused_res = await pause_lead("lead_f1", req=None, current_user=USER, db=db)
    assert paused_res["status"] == "paused"
    resumed_res = await resume_lead("lead_f1", current_user=USER, db=db)
    assert resumed_res["status"] == "resumed"

    camp_detail = await get_campaign("cmp_funnel_1", current_user=USER, db=db)
    assert "funnel_stages" in camp_detail
    assert camp_detail["funnel_stages"]["queued"] == 1
    assert camp_detail["funnel_stages"]["moving"] == 1
    assert camp_detail["funnel_stages"]["low_queue_warning"] is True
    assert len(camp_detail["list_performance"]) == 2

    analytics_res = await get_outreach_analytics(campaign_id="all", timeframe="30d", current_user=USER, db=db)
    assert "account_stats" in analytics_res
    assert analytics_res["account_stats"]["pending_invitations_count"] == 1
    assert "recent_activity" in analytics_res


@pytest.mark.asyncio
async def test_dripify_videos_13_to_16_parity():
    from outreach.core.dag_compiler import (
        find_missing_profile_variables,
        resolve_step_message_with_alternative,
    )
    from outreach.api.prompts import PromptPreviewRequest, preview_evaluated_message
    from outreach.api.inbox import (
        InboxLeadNoteRequest,
        add_thread_lead_note,
        get_thread,
        list_inbox_threads,
        mark_thread_unread,
    )
    from outreach.api.leads import (
        BlockLeadRequest,
        CreateCustomLeadFilterRequest,
        UpdateLeadProfileRequest,
        block_lead,
        create_custom_lead_filter,
        delete_custom_lead_filter,
        get_lead_activity,
        list_custom_lead_filters,
        list_leads,
        update_lead_profile,
        whitelist_lead,
    )

    db = MockDatabase()
    db.outreach_lead_notes = MockCollection()
    db.outreach_lead_custom_filters = MockCollection()
    db.outreach_do_not_contact = MockCollection()
    db.outreach_task_queue = MockCollection()
    db.outreach_lead_tag_definitions = MockCollection()

    # 1. Video #13: Alternative Message fallback when optional variable ({{company_name}} / {{company_followed}}) is missing
    lead_missing_company = {"first_name": "Sophia", "last_name": "Patel", "location": "Austin, TX"}
    missing_vars = find_missing_profile_variables(
        "Hi {{first_name}}, saw your work at {{company_name}} and that you follow {{company_followed}}!",
        lead_missing_company,
    )
    assert "company_name" in missing_vars
    assert "company_followed" in missing_vars

    res_alt = resolve_step_message_with_alternative(
        "Hi {{first_name}}, saw your work at {{company_name}}!",
        "Hi {{first_name}} in {{location}}, let's connect!",
        lead_missing_company,
    )
    assert res_alt["used_alternative"] is True
    assert res_alt["text"] == "Hi Sophia in Austin, TX, let's connect!"
    assert "company_name" in res_alt["missing_variables"]

    # Strict missing variable check when no alternative message is configured
    res_none = resolve_step_message_with_alternative(
        "Hi {{first_name}}, how are things at {{company_name}}?",
        "",
        lead_missing_company,
        strict_missing_check=True,
    )
    assert res_none["failed_missing_variable"] is True
    assert res_none["used_alternative"] is False
    assert res_none["missing_variables"] == ["company_name"]

    # Prompt preview endpoint returns used_alternative_message & missing_variables
    prev_alt = await preview_evaluated_message(
        PromptPreviewRequest(
            template="Hi {{first_name}} at {{company_name}}",
            alternative_message="Hi {{first_name}} from {{location}}!",
            custom_lead_data={"first_name": "Liam", "company_name": "", "location": "Chicago, IL"},
        ),
        current_user=USER,
        db=db,
    )
    assert prev_alt["used_alternative_message"] is True
    assert "company_name" in prev_alt["missing_variables"]
    assert prev_alt["evaluated_text"] == "Hi Liam from Chicago, IL!"

    # 2. Video #14: Smart Inbox Unread filter, Mark as Unread, and Synced Lead Profile Notes
    db.outreach_leads.items.append({
        "_id": "lead_doc_14",
        "id": "lead_14",
        "workspace_id": "ws_test_1",
        "campaign_id": "cmp_14",
        "first_name": "Noah",
        "last_name": "Kim",
        "company_name": "CloudNine",
        "location": "Seattle, WA",
        "linkedin_email": "noah@cloudnine.io",
        "linkedin_url": "https://www.linkedin.com/in/noah-kim",
        "execution_state": "messaged",
        "last_action_taken": "send_message",
        "is_connected": True,
    })
    db.outreach_inbox_threads.items.append({
        "_id": "th_doc_14",
        "id": "th_14",
        "workspace_id": "ws_test_1",
        "user_id": "user_test_1",
        "account_id": "acc_1",
        "lead_id": "lead_14",
        "lead_name": "Noah Kim",
        "unread_count": 0,
        "last_message_at": datetime.now(timezone.utc),
        "messages": [],
    })

    # Add note in Smart Inbox
    created_note = await add_thread_lead_note(
        "th_14",
        InboxLeadNoteRequest(body="Interested in Q1 enterprise rollout"),
        current_user=USER,
        db=db,
    )
    assert created_note["body"] == "Interested in Q1 enterprise rollout"

    # Verify thread detail hydrates lead contact info + synced notes
    full_thread = await get_thread("th_14", current_user=USER, db=db)
    assert full_thread["lead_company"] == "CloudNine"
    assert full_thread["lead_linkedin_email"] == "noah@cloudnine.io"
    assert len(full_thread["lead_notes"]) == 1
    assert full_thread["lead_notes"][0]["body"] == "Interested in Q1 enterprise rollout"

    # Verify note also appears on Lead Profile activity timeline
    act_res = await get_lead_activity("lead_14", skip=0, limit=50, current_user=USER, db=db)
    note_acts = [a for a in act_res["activities"] if a["kind"] == "note"]
    assert len(note_acts) == 1
    assert note_acts[0]["note"] == "Interested in Q1 enterprise rollout"

    # Mark thread as unread and filter by unread_only=True
    unread_res = await mark_thread_unread("th_14", current_user=USER, db=db)
    assert unread_res["unread_count"] == 1
    unread_threads = await list_inbox_threads(unread_only=True, skip=0, limit=50, current_user=USER, db=db)
    assert len(unread_threads) == 1
    assert unread_threads[0]["id"] == "th_14"

    # 3. Video #15 & #16: Working with Leads — Include/Exclude Custom Filters, Edit Lead Profile, Whitelist DNC
    db.outreach_leads.items.append({
        "_id": "lead_doc_15",
        "id": "lead_15",
        "workspace_id": "ws_test_1",
        "campaign_id": "cmp_14",
        "first_name": "Mia",
        "last_name": "Chen",
        "linkedin_url": "https://www.linkedin.com/in/mia-chen",
        "execution_state": "replied",
        "last_action_taken": "send_message",
        "is_connected": True,
    })

    # "Ignored Messages" filter: Include messaged, Exclude replied -> returns Noah (messaged) and excludes Mia (replied)
    ignored_res = await list_leads(
        include_actions="messaged",
        exclude_actions="replied",
        skip=0,
        limit=50,
        current_user=USER,
        db=db,
    )
    returned_ids = [l["id"] for l in ignored_res["leads"]]
    assert "lead_14" in returned_ids
    assert "lead_15" not in returned_ids

    # Save & list custom filter
    saved_cf = await create_custom_lead_filter(
        CreateCustomLeadFilterRequest(
            name="Ignored Messages",
            include_actions=["messaged"],
            exclude_actions=["replied"],
        ),
        current_user=USER,
        db=db,
    )
    assert saved_cf["name"] == "Ignored Messages"
    listed_cfs = await list_custom_lead_filters(current_user=USER, db=db)
    assert len(listed_cfs) == 1
    await delete_custom_lead_filter(saved_cf["id"], current_user=USER, db=db)

    # Edit Lead Profile fields (including university_name, company_followed, linkedin_email)
    updated_lead = await update_lead_profile(
        "lead_14",
        UpdateLeadProfileRequest(
            job_title="VP of Engineering",
            university_name="UC Berkeley",
            company_followed="OpenAI",
            linkedin_email="noah.kim@berkeley.edu",
        ),
        current_user=USER,
        db=db,
    )
    assert updated_lead["lead"]["job_title"] == "VP of Engineering"
    assert updated_lead["lead"]["university_name"] == "UC Berkeley"
    assert updated_lead["lead"]["company_followed"] == "OpenAI"
    assert updated_lead["lead"]["linkedin_email"] == "noah.kim@berkeley.edu"

    # Blacklist (DNC) and Whitelist Lead
    dnc_res = await block_lead("lead_14", BlockLeadRequest(), current_user=USER, db=db)
    assert dnc_res["status"] == "excluded"
    wl_res = await whitelist_lead("lead_14", current_user=USER, db=db)
    assert wl_res["do_not_contact"] is False
    assert wl_res["status"] == "whitelisted"


@pytest.mark.asyncio
async def test_dripify_videos_17_to_20_parity():
    """
    Tests for Dripify Videos #17, #18, #19, and #20:
    1. Video #20: Activity Control (connections_count, pending_sent_invitations throttle, account_type, previous_activity)
    2. Video #19: Team Management & Queue Health (empty_queue red, low_queue orange, healthy, unread_messages_count, inmails/follows)
    3. Video #19: Cross-Team Campaign Lead Deduplication (skip_team_campaign_leads)
    """
    from outreach.core.safety_shield import WarmUpGovernor
    from outreach.api.accounts import update_activity_control, ActivityControlRequest, list_outreach_accounts
    from outreach.api.analytics import get_outreach_analytics
    from outreach.core.lead_importer import LeadImporter

    # 1. Video #20: Activity Control safety shield with pending sent invitations throttling
    acc_healthy = {
        "id": "acc_v20",
        "workspace_id": "ws_test_1",
        "user_id": "user_test_1",
        "account_name": "Alex Morgan",
        "status": "active",
        "activity_control_enabled": True,
        "connections_count": 1200,
        "pending_invitations_count": 40,
        "premium_product": "sales_navigator",
        "warmup_started_at": datetime.now(timezone.utc) - timedelta(days=30),
        "daily_limits": {"connection_invites": 40, "messages": 60},
    }
    summary_healthy = WarmUpGovernor.compute_activity_control_summary(acc_healthy)
    assert summary_healthy["enabled"] is True
    assert summary_healthy["safety_status"] == "protected"
    assert summary_healthy["pending_invitations_throttled"] is False
    assert "pending_sent_invitations" in summary_healthy["factors_evaluated"]
    assert summary_healthy["recommended_limits"]["connection_invites"] == 40

    # High pending invitations (>= 150) automatically throttles connection_invites to 10/day
    acc_high_pending = {**acc_healthy, "pending_invitations_count": 165}
    summary_throttled = WarmUpGovernor.compute_activity_control_summary(acc_high_pending)
    assert summary_throttled["pending_invitations_throttled"] is True
    assert summary_throttled["safety_status"] == "throttled_safe_zone"
    assert summary_throttled["recommended_limits"]["connection_invites"] == 10

    # Test PATCH /accounts/{id}/activity-control endpoint
    db = MockDatabase()
    db.outreach_accounts = MockCollection()
    db.outreach_activity_logs = MockCollection()
    db.outreach_tasks = MockCollection()
    db.outreach_do_not_contact = MockCollection()
    db.outreach_accounts.items.append({**acc_healthy, "_id": "acc_doc_v20"})
    ac_res = await update_activity_control(
        "acc_v20",
        ActivityControlRequest(
            enabled=True,
            connections_count=1500,
            pending_invitations_count=120,
            premium_product="sales_navigator",
        ),
        current_user=USER,
        db=db,
    )
    assert ac_res["activity_control_enabled"] is True
    assert ac_res["activity_control"]["pending_invitations_count"] == 120
    assert ac_res["activity_control"]["pending_invitations_throttled"] is True
    assert ac_res["daily_limits"]["connection_invites"] == 15

    # Verify list_outreach_accounts exposes activity_control summary
    accounts_list = await list_outreach_accounts(current_user=USER, db=db)
    assert len(accounts_list) == 1
    assert accounts_list[0]["activity_control"]["enabled"] is True

    # 2. Video #19: Team Management & Queue Health (empty_queue, low_queue, unread_messages_count)
    db.outreach_accounts.items.append({
        "_id": "acc_doc_v19_2",
        "id": "acc_v19_2",
        "workspace_id": "ws_test_1",
        "user_id": "user_test_2",
        "account_name": "Jordan Lee",
        "status": "active",
        "activity_control_enabled": True,
        "connections_count": 600,
        "pending_invitations_count": 12,
    })
    # Campaign 1 for acc_v20: active, 0 queued leads -> empty_queue
    db.outreach_campaigns.items.append({
        "_id": "cmp_doc_v19_1",
        "id": "cmp_v19_1",
        "workspace_id": "ws_test_1",
        "name": "Alex Active Campaign",
        "status": "active",
        "sender_account_ids": ["acc_v20"],
        "skip_team_campaign_leads": True,
    })
    # Campaign 2 for acc_v19_2: active, 5 queued leads -> low_queue
    db.outreach_campaigns.items.append({
        "_id": "cmp_doc_v19_2",
        "id": "cmp_v19_2",
        "workspace_id": "ws_test_1",
        "name": "Jordan Active Campaign",
        "status": "active",
        "sender_account_ids": ["acc_v19_2"],
        "skip_team_campaign_leads": True,
    })
    for idx in range(5):
        db.outreach_leads.items.append({
            "_id": f"lead_doc_v19_{idx}",
            "id": f"lead_v19_{idx}",
            "workspace_id": "ws_test_1",
            "campaign_id": "cmp_v19_2",
            "first_name": f"Prospect{idx}",
            "linkedin_url": f"https://www.linkedin.com/in/prospect-{idx}",
            "execution_state": "queued",
        })
    # Unread inbox thread for acc_v20
    db.outreach_inbox_threads.items.append({
        "_id": "th_doc_v19",
        "id": "th_v19",
        "workspace_id": "ws_test_1",
        "account_id": "acc_v20",
        "lead_id": "lead_v19_0",
        "unread_count": 2,
    })

    analytics_res = await get_outreach_analytics(timeframe="30d", current_user=USER, db=db)
    team_perf = {tp["account_id"]: tp for tp in analytics_res["team_performance"]}
    assert team_perf["acc_v20"]["active_campaigns_count"] == 1
    assert team_perf["acc_v20"]["queued_leads_count"] == 0
    assert team_perf["acc_v20"]["queue_health_status"] == "empty_queue"
    assert team_perf["acc_v20"]["unread_messages_count"] == 1

    assert team_perf["acc_v19_2"]["active_campaigns_count"] == 1
    assert team_perf["acc_v19_2"]["queued_leads_count"] == 5
    assert team_perf["acc_v19_2"]["queue_health_status"] == "low_queue"

    # 3. Video #19: Cross-Team Campaign Lead Deduplication (skip_team_campaign_leads=True)
    # Create a draft campaign cmp_v19_3 for Alex with skip_team_campaign_leads=True
    db.outreach_campaigns.items.append({
        "_id": "cmp_doc_v19_3",
        "id": "cmp_v19_3",
        "workspace_id": "ws_test_1",
        "name": "Alex Draft Campaign",
        "status": "draft",
        "sender_account_ids": ["acc_v20"],
        "skip_team_campaign_leads": True,
    })
    db.outreach_email_suppressions = MockCollection()
    db.outreach_withdrawn_invites = MockCollection()

    # Try previewing prospect-0 (already in Jordan's campaign cmp_v19_2) into Alex's campaign cmp_v19_3
    preview_team_dedup = await LeadImporter.preview_leads(
        leads=[
            {"first_name": "Prospect0", "linkedin_url": "https://www.linkedin.com/in/prospect-0"},
            {"first_name": "BrandNew", "linkedin_url": "https://www.linkedin.com/in/brand-new-lead"},
        ],
        campaign_id="cmp_v19_3",
        workspace_id="ws_test_1",
        db=db,
        skip_team_campaign_leads=True,
    )
    assert preview_team_dedup["valid_count"] == 1
    assert preview_team_dedup["duplicate_count"] == 1
    rejected_rows = [r for r in preview_team_dedup["rows"] if r["status"] == "rejected"]
    assert len(rejected_rows) == 1
    assert rejected_rows[0]["rejection_code"] == "duplicate_team_campaign"

    ingest_team_dedup = await LeadImporter.ingest_leads(
        leads=[
            {"first_name": "Prospect0", "linkedin_url": "https://www.linkedin.com/in/prospect-0"},
            {"first_name": "BrandNew", "linkedin_url": "https://www.linkedin.com/in/brand-new-lead"},
        ],
        campaign_id="cmp_v19_3",
        workspace_id="ws_test_1",
        db=db,
        skip_team_campaign_leads=True,
        _ordered=True,
    )
    assert ingest_team_dedup["imported_count"] == 1
    assert ingest_team_dedup["duplicates_count"] == 1




