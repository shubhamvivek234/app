from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.routes.bulk_upload import (
    BulkPost,
    BulkScheduleRequest,
    CSV_TEMPLATE_COLUMNS,
    ValidateUrlsRequest,
    _layer7_validate,
    bulk_csv_schedule,
    download_csv_template,
    validate_bulk_urls,
)


class _FakeCursor:
    def __init__(self, items):
        self.items = items

    async def to_list(self, _length=None):
        return list(self.items)


class _FakeAccountsCollection:
    def __init__(self, accounts):
        self.accounts = accounts

    def find(self, query, projection=None):
        return _FakeCursor(self.accounts)


class _FakePostsCollection:
    def __init__(self, posts=None):
        self.posts = list(posts or [])
        self.inserted = []

    def find(self, query, projection=None):
        return _FakeCursor(self.posts)

    async def insert_many(self, docs, ordered=False):
        self.inserted.extend(docs)
        return SimpleNamespace(inserted_ids=[d.get("id") or d.get("post_id") for d in docs])


class _FakeDB:
    def __init__(self, accounts=None, posts=None):
        self.social_accounts = _FakeAccountsCollection(accounts or [])
        self.posts = _FakePostsCollection(posts or [])


def test_csv_template_contains_all_required_columns():
    expected = [
        "content", "platforms", "accounts", "scheduled_time", "timeslot_category",
        "timezone", "image_urls", "video_url", "title", "tags", "post_type",
    ]
    assert CSV_TEMPLATE_COLUMNS == expected


@pytest.mark.asyncio
async def test_validate_urls_blocks_ssrf():
    user = {"user_id": "u1"}
    req = ValidateUrlsRequest(urls=["http://127.0.0.1:8000/secret", "http://169.254.169.254/latest"])
    results = await validate_bulk_urls(req, current_user=user)
    assert len(results) == 2
    assert results[0].ok is False
    assert results[1].ok is False


@pytest.mark.asyncio
async def test_bulk_csv_schedule_creates_full_document_schema():
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    accounts = [
        {"id": "acc_ig", "username": "brand_ig", "display_name": "Brand IG", "platform": "instagram"},
        {"id": "acc_tw", "username": "brand_tw", "display_name": "Brand TW", "platform": "twitter"},
    ]
    fake_db = _FakeDB(accounts=accounts)
    user = {"user_id": "user_123", "default_workspace_id": "ws_123"}

    request = BulkScheduleRequest(
        posts=[
            BulkPost(
                content="Exciting news coming soon!",
                platforms=["instagram", "twitter"],
                accounts="Brand IG, Brand TW",
                scheduled_time=future_time,
                image_urls=["https://images.example.com/photo.jpg"],
                post_type="image",
                status="scheduled",
            )
        ]
    )

    response = await bulk_csv_schedule(request, current_user=user, db=fake_db)
    assert response.created == 1
    assert response.skipped == 0
    assert len(response.errors) == 0

    assert len(fake_db.posts.inserted) == 1
    doc = fake_db.posts.inserted[0]

    # Verify critical keys required across the application and Celery workers
    assert doc["id"] is not None
    assert doc["post_id"] == doc["id"]
    assert doc["version"] == 1
    assert doc["source"] == "csv_bulk_import"
    assert doc["user_id"] == "user_123"
    assert doc["workspace_id"] == "ws_123"
    assert doc["account_ids"] == ["acc_ig", "acc_tw"]
    assert doc["social_account_ids"] == ["acc_ig", "acc_tw"]
    assert doc["media_urls"] == ["https://images.example.com/photo.jpg"]
    assert doc["media_url"] == "https://images.example.com/photo.jpg"
    assert doc["platform_results"] == {"instagram": {"status": "pending"}, "twitter": {"status": "pending"}}
    assert "acc_ig" in doc["account_results"]
    assert "acc_tw" in doc["account_results"]
    assert len(doc["status_history"]) == 1
    assert doc["status_history"][0]["status"] == "scheduled"
    assert doc["content_hash"] is not None


@pytest.mark.asyncio
async def test_layer7_validate_detects_30_min_conflict():
    future = datetime.now(timezone.utc) + timedelta(days=2)
    accounts = [{"id": "acc_1", "username": "myacc", "display_name": "My Account", "platform": "twitter"}]
    existing_posts = [
        {"account_ids": ["acc_1"], "scheduled_time": future.isoformat(), "status": "scheduled"}
    ]
    fake_db = _FakeDB(accounts=accounts, posts=existing_posts)

    conflict_time = (future + timedelta(minutes=15)).isoformat()
    posts = [
        BulkPost(
            content="Conflicting post",
            platforms=["twitter"],
            accounts="My Account",
            scheduled_time=conflict_time,
            status="scheduled",
        )
    ]

    errors = await _layer7_validate(fake_db, "user_1", "ws_1", posts)
    assert len(errors) == 1
    assert "scheduled_time" in errors[0]
    assert "Conflict" in errors[0]["scheduled_time"]


@pytest.mark.asyncio
async def test_layer7_validate_rejects_missing_account():
    accounts = [{"id": "acc_1", "username": "real_acc", "display_name": "Real Acc", "platform": "twitter"}]
    fake_db = _FakeDB(accounts=accounts)

    posts = [
        BulkPost(
            content="Missing account post",
            platforms=["twitter"],
            accounts="non_existent_account",
            scheduled_time=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            status="scheduled",
        )
    ]

    errors = await _layer7_validate(fake_db, "user_1", "ws_1", posts)
    assert len(errors) == 1
    assert "accounts" in errors[0]
    assert "not found in workspace" in errors[0]["accounts"]
