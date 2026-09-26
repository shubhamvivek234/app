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
    CreateEngageDraftRequest,
    UpdateEngageDraftRequest,
    create_engage_draft,
    delete_engage_contact,
    delete_engage_list,
    EngageListSettingsRequest,
    get_engage_report,
    list_engage_drafts,
    update_engage_draft,
    update_engage_list_settings,
    router as engage_router,
)


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
    db.outreach_engage_posts.update_one.assert_not_awaited()


def make_db():
    db = SimpleNamespace()
    db.outreach_campaigns = SimpleNamespace(find_one=AsyncMock(return_value=None))
    db.outreach_engage_lists = SimpleNamespace(find_one=AsyncMock(return_value={
        "id": "list_1", "workspace_id": "workspace_1",
    }))
    db.outreach_engage_posts = SimpleNamespace(find_one=AsyncMock(return_value={
        "id": "post_1", "list_id": "list_1", "workspace_id": "workspace_1",
        "contact_id": "contact_1",
        "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:1/",
        "author_name": "Alex", "content_text": "A thoughtful post",
    }), update_one=AsyncMock())
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
    db.outreach_engage_posts.update_one.assert_not_awaited()


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
    db.outreach_engage_posts.update_one.assert_not_awaited()


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
        "list_id": "list_1", "workspace_id": "workspace_1",
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
        "contact_id": "contact_1", "list_id": "list_1", "workspace_id": "workspace_1",
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
