"""Draft-and-review Engage comments never perform LinkedIn actions."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from api.deps import get_current_user
from db.mongo import get_db

from outreach.api.engage import (
    AddContactsRequest,
    CreateEngageDraftRequest,
    PushContactsToCampaignRequest,
    UpdateEngageDraftRequest,
    add_contacts_to_list,
    create_engage_draft,
    delete_engage_contact,
    delete_engage_list,
    EngageListSettingsRequest,
    get_engage_list,
    get_engage_posts_feed,
    get_engage_report,
    list_engage_drafts,
    push_contacts_to_campaign,
    update_engage_draft,
    update_engage_list_settings,
    router as engage_router,
)
from celery_workers.tasks.engage import _run_scheduled_auto_fetches


USER = {"user_id": "owner", "default_workspace_id": "workspace_1"}


@pytest.mark.asyncio
async def test_review_draft_http_flow_returns_created_draft_without_linkedin_write():
    db = make_db()
    app = FastAPI()
    app.include_router(engage_router, prefix="/api/v1/outreach")
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/outreach/engage/lists/list_1/drafts",
            json={"post_id": "post_1", "comment_text": "A reviewed response"},
        )
        listing = await client.get("/api/v1/outreach/engage/lists/list_1/drafts")
    assert response.status_code == 201
    assert response.json()["contact_id"] == "contact_1"
    assert listing.status_code == 200
    assert db.outreach_engage_posts.update_one.await_args.args[1] == {"$inc": {"projection_revision": 1}}


def make_db():
    db = SimpleNamespace()
    db.outreach_campaigns = SimpleNamespace(find_one=AsyncMock(return_value=None))
    db.outreach_engage_lists = SimpleNamespace(find_one=AsyncMock(return_value={
        "_id": "list-source", "id": "list_1", "workspace_id": "workspace_1",
    }), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))
    db.outreach_engage_contacts = SimpleNamespace(find_one=AsyncMock(return_value={"_id": "contact-source", "id": "contact_1", "workspace_id": "workspace_1"}), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))
    db.outreach_engage_posts = SimpleNamespace(find_one=AsyncMock(return_value={
        "_id": "post-source", "id": "post_1", "list_id": "list_1", "workspace_id": "workspace_1",
        "contact_id": "contact_1",
        "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:1/",
        "author_name": "Alex", "content_text": "A thoughtful post",
    }), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))
    db.outreach_engage_drafts = SimpleNamespace(
        insert_one=AsyncMock(), find_one=AsyncMock(), update_one=AsyncMock(),
        find=lambda *args, **kwargs: SimpleNamespace(
            sort=lambda *a, **kw: SimpleNamespace(to_list=AsyncMock(return_value=[])),
        ),
        count_documents=AsyncMock(return_value=0),
    )
    return db


@pytest.mark.asyncio
async def test_create_draft_saves_review_text_without_publishing():
    db = make_db()
    result = await create_engage_draft(
        "list_1", CreateEngageDraftRequest(post_id="post_1", comment_text="My considered reply"),
        current_user=USER, db=db,
    )
    assert result["status"] == "pending"
    assert result["comment_text"] == "My considered reply"
    assert result["source"] == "manual_review"
    assert result["contact_id"] == "contact_1"
    db.outreach_engage_drafts.insert_one.assert_awaited_once()
    assert db.outreach_engage_posts.update_one.await_args.args[1] == {"$inc": {"projection_revision": 1}}


@pytest.mark.asyncio
async def test_create_draft_rejects_post_outside_list():
    db = make_db()
    db.outreach_engage_posts.find_one.return_value = None
    with pytest.raises(HTTPException) as error:
        await create_engage_draft(
            "list_1", CreateEngageDraftRequest(post_id="foreign", comment_text="No"),
            current_user=USER, db=db,
        )
    assert error.value.status_code == 404
    db.outreach_engage_drafts.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_draft_edit_and_self_report_do_not_change_confirmed_post():
    db = make_db()
    db.outreach_engage_drafts.find_one.return_value = {
        "id": "draft_1", "list_id": "list_1", "workspace_id": "workspace_1",
        "post_id": "post_1", "status": "pending", "comment_text": "Before",
    }
    db.outreach_engage_drafts.update_one.return_value = SimpleNamespace(modified_count=1)
    result = await update_engage_draft(
        "list_1", "draft_1", UpdateEngageDraftRequest(comment_text="After", status="completed"),
        current_user=USER, db=db,
    )
    assert result["status"] == "completed"
    assert result["completion_source"] == "self_reported"
    assert db.outreach_engage_posts.update_one.await_args.args[1] == {"$inc": {"projection_revision": 1}}


@pytest.mark.asyncio
async def test_draft_list_is_scoped_and_status_validated():
    db = make_db()
    result = await list_engage_drafts("list_1", current_user=USER, db=db)
    assert result == {"drafts": [], "pending_count": 0}
    assert db.outreach_engage_drafts.count_documents.await_args.args[0]["workspace_id"] == "workspace_1"
    with pytest.raises(HTTPException) as error:
        await update_engage_draft(
            "list_1", "draft_1", UpdateEngageDraftRequest(status="published"),
            current_user=USER, db=db,
        )
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_report_counts_only_confirmed_linkedin_events():
    db = make_db()
    now = datetime.now(timezone.utc)
    posts = [
        {"contact_id": "c1", "status": "commented", "liked_at": now, "commented_at": now},
        {"contact_id": "c2", "status": "liked", "liked_at": now},
        {"contact_id": "c3", "status": "commented"},  # legacy status without confirmation
    ]
    db.outreach_engage_posts.find = lambda *args, **kwargs: SimpleNamespace(
        to_list=AsyncMock(return_value=posts),
    )
    db.outreach_engage_contacts = SimpleNamespace(count_documents=AsyncMock(return_value=3))
    report = await get_engage_report("list_1", current_user=USER, db=db)
    assert report["likes_sent"] == 2
    assert report["comments_published"] == 1
    assert report["contacts_engaged"] == 2
    assert "response_rate" not in report


@pytest.mark.asyncio
async def test_deleting_list_cascades_to_review_drafts():
    db = make_db()
    db.outreach_engage_lists.delete_one = AsyncMock(return_value=SimpleNamespace(deleted_count=1))
    db.outreach_engage_contacts = SimpleNamespace(delete_many=AsyncMock())
    db.outreach_engage_posts.delete_many = AsyncMock()
    db.outreach_engage_drafts.delete_many = AsyncMock()
    await delete_engage_list("list_1", current_user=USER, db=db)
    db.outreach_engage_drafts.delete_many.assert_awaited_once_with({
        "list_id": "list_1", "workspace_id": "workspace_1", "workspace_id.0": {"$exists": False},
    })


@pytest.mark.asyncio
async def test_deleting_contact_cascades_to_its_review_drafts():
    db = make_db()
    db.outreach_engage_contacts = SimpleNamespace(
        delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=1)),
        count_documents=AsyncMock(return_value=0),
    )
    db.outreach_engage_posts.delete_many = AsyncMock()
    db.outreach_engage_posts.count_documents = AsyncMock(return_value=0)
    db.outreach_engage_drafts.delete_many = AsyncMock()
    db.outreach_engage_lists.update_one = AsyncMock()
    await delete_engage_contact("list_1", "contact_1", current_user=USER, db=db)
    db.outreach_engage_drafts.delete_many.assert_awaited_once_with({
        "contact_id": "contact_1", "list_id": "list_1", "workspace_id": "workspace_1", "workspace_id.0": {"$exists": False},
    })


@pytest.mark.asyncio
async def test_armed_list_cannot_be_unlinked_or_deleted_until_launch_is_canceled():
    db = make_db()
    db.outreach_engage_lists.find_one.return_value = {
        "id": "list_1", "workspace_id": "workspace_1", "campaign_id": "campaign_1",
        "warmup_hours": 24,
    }
    db.outreach_campaigns = SimpleNamespace(find_one=AsyncMock(return_value={
        "id": "campaign_1", "workspace_id": "workspace_1", "status": "warming_up",
        "auto_launch_enabled": True, "auto_launch_list_id": "list_1",
    }))
    db.outreach_engage_lists.update_one = AsyncMock()
    db.outreach_engage_lists.delete_one = AsyncMock()
    with pytest.raises(HTTPException) as unlink_error:
        await update_engage_list_settings(
            "list_1", EngageListSettingsRequest(campaign_id=None, warmup_hours=48),
            current_user=USER, db=db,
        )
    with pytest.raises(HTTPException) as delete_error:
        await delete_engage_list("list_1", current_user=USER, db=db)
    assert unlink_error.value.status_code == delete_error.value.status_code == 409
    db.outreach_engage_lists.update_one.assert_not_awaited()
    db.outreach_engage_lists.delete_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_list_settings_supports_metadata_and_auto_fetch_without_overwriting_campaign():
    db = make_db()
    db.outreach_engage_lists.find_one.return_value = {
        "_id": "list-source", "id": "list_1", "workspace_id": "workspace_1",
        "name": "Old Name", "emoji": "🎯", "description": "Old",
        "campaign_id": "campaign_1", "warmup_hours": 48,
        "auto_fetch_enabled": False, "auto_fetch_account_id": None,
    }
    res = await update_engage_list_settings(
        "list_1",
        EngageListSettingsRequest(
            name="Renamed List", emoji="🚀", description="New desc",
            auto_fetch_enabled=True, auto_fetch_account_id="acc_1",
        ),
        current_user=USER, db=db,
    )
    assert res["name"] == "Renamed List"
    assert res["emoji"] == "🚀"
    assert res["description"] == "New desc"
    assert res["auto_fetch_enabled"] is True
    assert res["auto_fetch_account_id"] == "acc_1"
    assert "campaign_id" not in res
    update_doc = db.outreach_engage_lists.update_one.await_args.args[1]["$set"]
    assert "campaign_id" not in update_doc
    assert "warmup_hours" not in update_doc


@pytest.mark.asyncio
async def test_update_draft_marks_linkedin_confirmed_when_post_commented_at_present():
    db = make_db()
    now = datetime.now(timezone.utc)
    db.outreach_engage_posts.find_one.return_value = {
        "_id": "post-source", "id": "post_1", "list_id": "list_1",
        "workspace_id": "workspace_1", "status": "commented", "commented_at": now,
    }
    db.outreach_engage_drafts.find_one.return_value = {
        "id": "draft_1", "list_id": "list_1", "workspace_id": "workspace_1",
        "post_id": "post_1", "status": "pending", "comment_text": "Approved reply",
    }
    db.outreach_engage_drafts.update_one.return_value = SimpleNamespace(modified_count=1)
    result = await update_engage_draft(
        "list_1", "draft_1",
        UpdateEngageDraftRequest(comment_text="Approved reply", status="completed"),
        current_user=USER, db=db,
    )
    assert result["status"] == "completed"
    assert result["completion_source"] == "linkedin_confirmed"


@pytest.mark.asyncio
async def test_get_engage_list_computes_per_contact_warmup_status():
    db = make_db()
    now = datetime.now(timezone.utc)
    contacts = [
        {"id": "c_warm", "list_id": "list_1", "workspace_id": "workspace_1", "full_name": "Alice"},
        {"id": "c_needs", "list_id": "list_1", "workspace_id": "workspace_1", "full_name": "Bob"},
        {"id": "c_none", "list_id": "list_1", "workspace_id": "workspace_1", "full_name": "Charlie"},
    ]
    posts = [
        {"contact_id": "c_warm", "status": "commented", "commented_at": now, "liked_at": None},
        {"contact_id": "c_needs", "status": "pending", "commented_at": None, "liked_at": None},
    ]
    db.outreach_engage_contacts.find = lambda *a, **kw: SimpleNamespace(
        to_list=AsyncMock(return_value=contacts),
    )
    db.outreach_engage_posts.find = lambda *a, **kw: SimpleNamespace(
        to_list=AsyncMock(return_value=posts),
    )
    detail = await get_engage_list("list_1", current_user=USER, db=db)
    assert detail["warmed_up_contacts_count"] == 1
    by_id = {c["id"]: c for c in detail["contacts"]}
    assert by_id["c_warm"]["warmup_status"] == "warmed_up"
    assert by_id["c_needs"]["warmup_status"] == "needs_engagement"
    assert by_id["c_none"]["warmup_status"] == "no_recent_posts"


@pytest.mark.asyncio
async def test_add_contacts_imports_leads_from_campaign_and_links_draft_campaign():
    db = make_db()
    db.outreach_campaigns.find_one = AsyncMock(side_effect=[
        None,
        {"id": "camp_1", "workspace_id": "workspace_1", "status": "draft"},
    ])
    db.outreach_leads = SimpleNamespace(
        find=lambda *a, **kw: SimpleNamespace(to_list=AsyncMock(return_value=[
            {"linkedin_url": "https://www.linkedin.com/in/alice-smith/"},
            {"linkedin_url": "https://www.linkedin.com/in/bob-jones/"},
        ])),
    )
    db.outreach_engage_contacts = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
        find=lambda *a, **kw: SimpleNamespace(to_list=AsyncMock(return_value=[])),
        insert_one=AsyncMock(),
        count_documents=AsyncMock(return_value=0),
    )
    db.outreach_accounts = SimpleNamespace(find_one=AsyncMock(return_value=None))
    result = await add_contacts_to_list(
        "list_1",
        AddContactsRequest(source_campaign_id="camp_1", link_warmup_campaign=True),
        current_user=USER, db=db,
    )
    assert result["added_count"] == 2
    assert db.outreach_engage_contacts.insert_one.await_count == 2


@pytest.mark.asyncio
async def test_push_contacts_to_campaign_inserts_warmed_up_contacts():
    db = make_db()
    now = datetime.now(timezone.utc)
    db.outreach_campaigns.find_one = AsyncMock(return_value={
        "id": "camp_target", "workspace_id": "workspace_1", "status": "draft", "total_leads": 0,
    })
    db.outreach_campaigns.update_one = AsyncMock()
    db.outreach_engage_contacts.find = lambda *a, **kw: SimpleNamespace(
        to_list=AsyncMock(return_value=[
            {"id": "c1", "full_name": "Alice Smith", "profile_url": "https://www.linkedin.com/in/alice-smith", "headline": "CEO", "enrichment_status": "verified"},
            {"id": "c2", "full_name": "Bob Jones", "profile_url": "https://www.linkedin.com/in/bob-jones", "headline": "CTO", "enrichment_status": "verified"},
        ]),
    )
    db.outreach_engage_posts.find = lambda *a, **kw: SimpleNamespace(
        to_list=AsyncMock(return_value=[
            {"contact_id": "c1", "status": "liked", "liked_at": now, "commented_at": None},
        ]),
    )
    db.outreach_leads = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
        find=lambda *a, **kw: SimpleNamespace(to_list=AsyncMock(return_value=[])),
        insert_one=AsyncMock(),
        count_documents=AsyncMock(return_value=1),
    )
    res = await push_contacts_to_campaign(
        "list_1",
        PushContactsToCampaignRequest(campaign_id="camp_target", only_warmed_up=True),
        current_user=USER, db=db,
    )
    assert res["pushed_count"] == 1
    assert res["campaign_id"] == "camp_target"
    db.outreach_leads.insert_one.assert_awaited_once()
    inserted_lead = db.outreach_leads.insert_one.await_args.args[0]
    assert inserted_lead["first_name"] == "Alice"
    assert inserted_lead["last_name"] == "Smith"


@pytest.mark.asyncio
async def test_get_engage_posts_feed_supports_search_contact_and_sort():
    db = make_db()
    db.outreach_engage_posts.count_documents = AsyncMock(return_value=1)
    captured_query = {}
    captured_sort = []

    def fake_find(query, projection=None):
        captured_query.update(query)
        return SimpleNamespace(
            sort=lambda field, direction: (
                captured_sort.append((field, direction))
                or SimpleNamespace(
                    skip=lambda s: SimpleNamespace(
                        limit=lambda l: SimpleNamespace(to_list=AsyncMock(return_value=[{"id": "post_1"}]))
                    )
                )
            )
        )

    db.outreach_engage_posts.find = fake_find
    res = await get_engage_posts_feed(
        "list_1", status_filter="pending", contact_id="contact_1",
        search="growth", sort_by="reactions", fresh_only=True,
        skip=0, limit=20, current_user=USER, db=db,
    )
    assert res["total"] == 1
    assert captured_query["contact_id"] == "contact_1"
    assert "$or" in captured_query
    assert captured_sort == [("reactions_count", -1)]


@pytest.mark.asyncio
async def test_scheduled_auto_fetch_queues_due_lists(monkeypatch):
    fake_db = SimpleNamespace()
    fake_db.outreach_engage_lists = SimpleNamespace(
        find=lambda *a, **kw: SimpleNamespace(
            limit=lambda l: SimpleNamespace(
                to_list=AsyncMock(return_value=[{
                    "_id": "oid_1", "id": "list_1", "user_id": "owner", "workspace_id": "workspace_1",
                    "auto_fetch_enabled": True, "auto_fetch_account_id": "acc_1",
                    "fetch_status": "idle", "last_auto_fetched_at": None,
                }])
            )
        ),
        find_one=AsyncMock(return_value={
            "_id": "oid_1", "id": "list_1", "workspace_id": "workspace_1",
        }),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1, modified_count=1)),
    )
    fake_db.outreach_accounts = SimpleNamespace(
        find_one=AsyncMock(return_value={
            "id": "acc_1", "workspace_id": "workspace_1", "status": "active",
            "working_hours_start": "00:00", "working_hours_end": "23:59",
            "working_timezone": "UTC",
        }),
    )
    fake_db.outreach_engage_contacts = SimpleNamespace(count_documents=AsyncMock(return_value=3))

    queued_calls = []
    monkeypatch.setattr("outreach.core.paid_access.live_actions_enabled", lambda: True)
    monkeypatch.setattr("celery_workers.tasks.engage.sender_is_ready", AsyncMock(return_value=True))
    monkeypatch.setattr("outreach.core.rate_limiter.OutboundRateLimiter.is_within_working_hours", staticmethod(lambda s, n: True))
    monkeypatch.setattr(
        "celery_workers.tasks.engage.celery_app.send_task",
        lambda name, args=None, **kwargs: queued_calls.append((name, args)),
    )
    result = await _run_scheduled_auto_fetches(db=fake_db)
    assert result["queued"] == 1
    assert len(queued_calls) == 1
    assert queued_calls[0][0] == "celery_workers.tasks.engage.fetch_posts"
    assert queued_calls[0][1][:3] == ["list_1", "workspace_1", "acc_1"]
