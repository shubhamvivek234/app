import io
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import UploadFile
from starlette.requests import Request

from api.routes import public_api as public_route


class _FakeMediaAssetsCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(doc)
        return MagicMock(inserted_id=doc.get("id"))


class _FakeClippingJobsCollection:
    def __init__(self):
        self.jobs = {}

    async def insert_one(self, doc):
        self.jobs[doc["id"]] = doc
        return MagicMock(inserted_id=doc["id"])

    async def find_one(self, query, projection=None):
        job_id = query.get("id")
        return self.jobs.get(job_id)


class _FakeSocialAccountsCollection:
    def __init__(self, accounts=None):
        self.accounts = {a["id"]: a for a in (accounts or [])}

    async def find_one(self, query, projection=None):
        acc_id = query.get("id")
        return self.accounts.get(acc_id)


class _FakePostsCollection:
    def __init__(self, posts=None):
        self.posts = {p["id"]: p for p in (posts or [])}

    async def find_one(self, query, projection=None):
        post_id = query.get("id")
        return self.posts.get(post_id)

    def find(self, query, projection=None):
        items = [p for p in self.posts.values() if p.get("workspace_id") == query.get("workspace_id")]
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=items)
        return mock_cursor


class _FakeDB:
    def __init__(self):
        self.media_assets = _FakeMediaAssetsCollection()
        self.clipping_jobs = _FakeClippingJobsCollection()
        self.social_accounts = _FakeSocialAccountsCollection([
            {
                "id": "acc_x_1",
                "workspace_id": "ws_1",
                "platform": "twitter",
                "platform_username": "unravler_app",
                "followers_count": 1250,
            }
        ])
        self.posts = _FakePostsCollection([
            {
                "id": "post_123",
                "workspace_id": "ws_1",
                "account_ids": ["acc_x_1"],
                "status": "published",
                "likes": 42,
                "comments_count": 8,
                "shares": 5,
            }
        ])


def _fake_request():
    scope = {"type": "http", "method": "POST", "path": "/api/public/test", "headers": []}
    return Request(scope)


@pytest.mark.asyncio
async def test_public_upload_media_success():
    fake_db = _FakeDB()
    req = _fake_request()
    file_bytes = b"fake image content PNG..."
    upload_file = UploadFile(filename="banner.png", file=io.BytesIO(file_bytes))

    with patch("api.routes.public_api._resolve_public_principal", new_callable=AsyncMock) as mock_principal, \
         patch("utils.storage.upload_file_async", new_callable=AsyncMock) as mock_storage:
        
        mock_principal.return_value = ({}, {"user_id": "usr_1", "default_workspace_id": "ws_1"})
        mock_storage.return_value = "https://cdn.unravler.com/media/usr_1/banner.png"

        res = await public_route.public_upload_media(
            request=req,
            file=upload_file,
            db=fake_db,
            authorization="Bearer token_123",
        )

        assert res["url"] == "https://cdn.unravler.com/media/usr_1/banner.png"
        assert res["path"] == "https://cdn.unravler.com/media/usr_1/banner.png"
        assert res["filename"].endswith(".png")
        assert len(fake_db.media_assets.docs) == 1
        assert fake_db.media_assets.docs[0]["workspace_id"] == "ws_1"


@pytest.mark.asyncio
async def test_public_generate_image_success():
    fake_db = _FakeDB()
    req = _fake_request()
    payload = public_route.PublicGenerateImageRequest(prompt="AI startup launch", style="editorial")

    with patch("api.routes.public_api._resolve_public_principal", new_callable=AsyncMock) as mock_principal:
        mock_principal.return_value = ({}, {"user_id": "usr_1", "default_workspace_id": "ws_1"})

        res = await public_route.public_generate_image(
            request=req,
            payload=payload,
            db=fake_db,
            authorization="Bearer token_123",
        )

        assert res["id"].startswith("img_")
        assert "pollinations.ai" in res["url"]
        assert res["prompt"] == "AI startup launch"


@pytest.mark.asyncio
async def test_public_create_and_get_clipping_job():
    fake_db = _FakeDB()
    req = _fake_request()
    payload = public_route.PublicClippingRequest(
        youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        num_clips=3,
        fit_mode="blur",
        target_platforms=["tiktok", "instagram"],
    )

    with patch("api.routes.public_api._resolve_public_principal", new_callable=AsyncMock) as mock_principal, \
         patch("celery_workers.tasks.clipping.process_clipping_job.delay", MagicMock()):
        
        mock_principal.return_value = ({}, {"user_id": "usr_1", "default_workspace_id": "ws_1"})

        created_job = await public_route.public_create_clipping_job(
            request=req,
            payload=payload,
            db=fake_db,
            authorization="Bearer token_123",
        )

        assert created_job["status"] == "queued"
        assert created_job["num_clips"] == 3
        job_id = created_job["id"]

        # Now inspect through get_clipping_job
        fetched = await public_route.public_get_clipping_job(
            request=req,
            job_id=job_id,
            db=fake_db,
            authorization="Bearer token_123",
        )
        assert fetched["id"] == job_id
        assert fetched["youtube_url"] == payload.youtube_url


@pytest.mark.asyncio
async def test_public_platform_and_post_analytics():
    fake_db = _FakeDB()
    req = _fake_request()

    with patch("api.routes.public_api._resolve_public_principal", new_callable=AsyncMock) as mock_principal:
        mock_principal.return_value = ({}, {"user_id": "usr_1", "default_workspace_id": "ws_1"})

        # Platform analytics
        platform_metrics = await public_route.public_platform_analytics(
            request=req,
            account_id="acc_x_1",
            db=fake_db,
            days=7,
            authorization="Bearer token_123",
        )

        labels = [m["label"] for m in platform_metrics]
        assert "Followers" in labels
        assert "Impressions" in labels
        assert "Engagement" in labels
        assert len(platform_metrics[0]["data"]) == 7

        # Post analytics
        post_metrics = await public_route.public_post_analytics(
            request=req,
            post_id="post_123",
            db=fake_db,
            days=7,
            authorization="Bearer token_123",
        )

        post_labels = [m["label"] for m in post_metrics]
        assert "Likes" in post_labels
        assert "Comments" in post_labels
        assert "Shares" in post_labels
        likes_series = next(m for m in post_metrics if m["label"] == "Likes")
        assert likes_series["data"][-1]["total"] == 42
