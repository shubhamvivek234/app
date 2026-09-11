import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock
from bson import ObjectId
from fastapi import HTTPException

from api.routes.bio_pages import (
    _is_block_active,
    BioPageConfig,
    BioBlockItem,
    BioSubPage,
    BioTheme,
    PageSchedule,
    get_my_bio_page,
    save_my_bio_page,
    get_public_bio_page,
    track_bio_link_click,
    subscribe_to_bio_newsletter,
    delete_my_bio_page,
)


class _FakeCursor:
    def __init__(self, items):
        self.items = items

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, length=100):
        return self.items

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeCollection:
    def __init__(self, items=None):
        self.items = items or []
        self.inserted = []

    async def find_one(self, query):
        for item in self.items:
            matched = True
            for k, v in query.items():
                if k == "$or":
                    or_matched = any(
                        all(item.get(subk) == subv for subk, subv in cond.items())
                        for cond in v
                    )
                    if not or_matched:
                        matched = False
                        break
                elif isinstance(v, dict):
                    if "$ne" in v and item.get(k) == v["$ne"]:
                        matched = False
                        break
                elif item.get(k) != v:
                    matched = False
                    break
            if matched:
                return item
        return None

    def find(self, query=None, projection=None):
        matched_items = []
        for item in self.items:
            if query and "status" in query and item.get("status") != query["status"]:
                continue
            matched_items.append(item)
        return _FakeCursor(matched_items)

    async def insert_one(self, doc):
        self.inserted.append(doc)
        self.items.append(doc)
        return type("Result", (), {"inserted_id": doc.get("_id", ObjectId())})()

    async def update_one(self, query, update, upsert=False):
        doc = await self.find_one(query)
        if doc:
            if "$set" in update:
                doc.update(update["$set"])
            if "$inc" in update:
                for k, inc_val in update["$inc"].items():
                    doc[k] = doc.get(k, 0) + inc_val
            return type("Result", (), {"matched_count": 1, "modified_count": 1})()
        elif upsert:
            new_doc = {}
            if "$set" in update:
                new_doc.update(update["$set"])
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            self.items.append(new_doc)
            return type("Result", (), {"matched_count": 0, "upserted_id": ObjectId()})()
        return type("Result", (), {"matched_count": 0, "modified_count": 0})()

    async def delete_one(self, query):
        doc = await self.find_one(query)
        if doc and doc in self.items:
            self.items.remove(doc)
            return type("Result", (), {"deleted_count": 1})()
        return type("Result", (), {"deleted_count": 0})()

    async def delete_many(self, query):
        initial_len = len(self.items)
        if not query:
            self.items.clear()
            return type("Result", (), {"deleted_count": initial_len})()
        k, v = list(query.items())[0]
        self.items = [item for item in self.items if item.get(k) != v]
        return type("Result", (), {"deleted_count": initial_len - len(self.items)})()

    async def aggregate(self, pipeline):
        return _FakeCursor([])


class _FakeDB:
    def __init__(self):
        self.bio_pages = _FakeCollection()
        self.posts = _FakeCollection()
        self.workspace_leads = _FakeCollection()
        self.bio_analytics = _FakeCollection()
        self.users = _FakeCollection()


def test_is_block_active_schedule():
    now = datetime.now(timezone.utc)
    
    # Active without schedule
    assert _is_block_active({"active": True}, now) is True
    # Inactive
    assert _is_block_active({"active": False}, now) is False
    
    # Active inside schedule window
    schedule_valid = {
        "active": True,
        "schedule": {
            "start_at": now - timedelta(hours=1),
            "end_at": now + timedelta(hours=1),
        }
    }
    assert _is_block_active(schedule_valid, now) is True

    # Inactive because expired
    schedule_expired = {
        "active": True,
        "schedule": {
            "start_at": now - timedelta(days=2),
            "end_at": now - timedelta(days=1),
        }
    }
    assert _is_block_active(schedule_expired, now) is False


@pytest.mark.asyncio
async def test_bio_page_crud_and_public_view():
    db = _FakeDB()
    user = {"user_id": "usr_creator1", "default_workspace_id": "ws_creator1", "name": "Alex Designer"}

    # 1. Get default bio page
    bio = await get_my_bio_page(current_user=user, db=db)
    assert bio["handle"] is not None
    assert len(bio["blocks"]) >= 2

    # 2. Save custom bio page
    config = BioPageConfig(
        handle="alex_design",
        title="Alex Jenkins",
        bio="Official Links & Design Drops ✨",
        avatar_url="https://example.com/avatar.jpg",
        verified_badge=True,
        theme=BioTheme(preset="editorial_cream"),
        blocks=[
            BioBlockItem(id="b1", type="link", title="My Portfolio", url="https://alex.design", badge="Featured"),
            BioBlockItem(id="b2", type="lead_capture", headline="Join My Newsletter 💌"),
        ],
        social_links={"instagram": "https://instagram.com/alex", "youtube": "https://youtube.com/@alex"},
        custom_domain="links.alex.design",
    )
    save_res = await save_my_bio_page(config, current_user=user, db=db)
    assert save_res["ok"] is True
    assert save_res["handle"] == "alex_design"

    # 3. Public read
    public_page = await get_public_bio_page(handle="alex_design", db=db)
    assert public_page["title"] == "Alex Jenkins"
    assert public_page["verified_badge"] is True
    assert len(public_page["blocks"]) == 2

    # 4. Subscribe lead
    lead_res = await subscribe_to_bio_newsletter(
        handle="alex_design",
        body=type("Req", (), {"email": "fan@gmail.com", "source_block_id": "b2"})(),
        db=db,
    )
    assert lead_res["ok"] is True
    assert len(db.workspace_leads.items) == 1
    assert db.workspace_leads.items[0]["email"] == "fan@gmail.com"


@pytest.mark.asyncio
async def test_bio_page_scheduling_window():
    db = _FakeDB()
    user = {"user_id": "usr_sched1", "default_workspace_id": "ws_sched1", "name": "Scheduled Creator"}
    now = datetime.now(timezone.utc)

    # 1. Config with future start_at -> 404 scheduled
    future_config = BioPageConfig(
        handle="future_launch",
        title="Upcoming Bio",
        page_schedule=PageSchedule(
            enabled=True,
            start_at=now + timedelta(days=2),
            end_at=now + timedelta(days=5),
        ),
    )
    await save_my_bio_page(future_config, current_user=user, db=db)

    with pytest.raises(HTTPException) as exc_info:
        await get_public_bio_page(handle="future_launch", db=db)
    assert exc_info.value.status_code == 404
    assert "scheduled to go live" in exc_info.value.detail.lower()

    # 2. Config with past end_at -> 404 expired
    expired_config = BioPageConfig(
        handle="future_launch",
        title="Expired Bio",
        page_schedule=PageSchedule(
            enabled=True,
            start_at=now - timedelta(days=5),
            end_at=now - timedelta(days=1),
        ),
    )
    await save_my_bio_page(expired_config, current_user=user, db=db)

    with pytest.raises(HTTPException) as exc_info:
        await get_public_bio_page(handle="future_launch", db=db)
    assert exc_info.value.status_code == 404
    assert "expired on" in exc_info.value.detail.lower()

    # 3. Config with valid current window -> 200 OK
    live_config = BioPageConfig(
        handle="future_launch",
        title="Live Timed Bio",
        page_schedule=PageSchedule(
            enabled=True,
            start_at=now - timedelta(hours=2),
            end_at=now + timedelta(hours=2),
        ),
    )
    await save_my_bio_page(live_config, current_user=user, db=db)
    pub = await get_public_bio_page(handle="future_launch", db=db)
    assert pub["title"] == "Live Timed Bio"


@pytest.mark.asyncio
async def test_bio_page_permanent_deletion():
    db = _FakeDB()
    user = {"user_id": "usr_del1", "default_workspace_id": "ws_del1", "name": "Deleting Creator"}

    # 1. Setup page with lead
    config = BioPageConfig(
        handle="to_delete_page",
        title="To Be Erased",
    )
    await save_my_bio_page(config, current_user=user, db=db)
    page_doc = await db.bio_pages.find_one({"handle": "to_delete_page"})
    page_id = page_doc["_id"]

    # Insert lead and analytics record
    await db.workspace_leads.insert_one({"page_id": page_id, "email": "lead@test.com"})
    await db.bio_analytics.insert_one({"page_id": page_id, "event_type": "click"})

    assert len(db.bio_pages.items) == 1
    assert len(db.workspace_leads.items) == 1
    assert len(db.bio_analytics.items) == 1

    # 2. Call delete_my_bio_page
    del_res = await delete_my_bio_page(current_user=user, db=db)
    assert del_res["success"] is True
    assert "permanently deleted" in del_res["message"]

    # 3. Verify clean deletion
    assert len(db.bio_pages.items) == 0
    assert len(db.workspace_leads.items) == 0
    assert len(db.bio_analytics.items) == 0

    # 4. Public access now returns 404
    with pytest.raises(HTTPException) as exc_info:
        await get_public_bio_page(handle="to_delete_page", db=db)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_bio_subpage_isolation_and_save():
    """Verify that multi-page sub-pages isolate blocks and metadata without bleed."""
    db = _FakeDB()
    user = {"user_id": "usr_sub1", "default_workspace_id": "ws_sub1", "name": "Multi-Page Creator"}

    home_block = BioBlockItem(
        id="blk_home_1",
        type="link",
        title="Official Website",
        url="https://example.com",
        active=True,
    )
    shop_block = BioBlockItem(
        id="blk_shop_1",
        type="link",
        title="Merch Store",
        url="https://shop.example.com",
        active=True,
    )

    home_page = BioSubPage(
        id="home",
        title="Main Profile",
        slug="home",
        description="Creator Main Profile",
        blocks=[home_block],
    )
    shop_theme = BioTheme(background_color="#123456", card_style="glass")
    shop_page = BioSubPage(
        id="page_shop",
        title="Shop Page",
        slug="shop",
        description="Exclusive Merch",
        avatar_url="https://cdn.example.com/shop_avatar.png",
        theme=shop_theme,
        blocks=[shop_block],
    )

    config = BioPageConfig(
        handle="multipage_creator",
        title="Multi-Page Creator",
        bio="Welcome to all my pages",
        blocks=[home_block],
        pages=[home_page, shop_page],
        active_page_id="page_shop",
        is_published=True,
    )

    # Save to backend
    save_res = await save_my_bio_page(config, current_user=user, db=db)
    assert save_res["ok"] is True

    # 1. Verify saved doc has isolated blocks, theme, and avatar per page
    saved_doc = await db.bio_pages.find_one({"handle": "multipage_creator"})
    assert saved_doc is not None
    # Root blocks belong strictly to Home
    assert len(saved_doc["blocks"]) == 1
    assert saved_doc["blocks"][0]["id"] == "blk_home_1"

    # Pages list preserves both pages independently
    assert len(saved_doc["pages"]) == 2
    saved_home = next(p for p in saved_doc["pages"] if p["id"] == "home")
    saved_shop = next(p for p in saved_doc["pages"] if p["id"] == "page_shop")

    assert saved_home["title"] == "Main Profile"
    assert len(saved_home["blocks"]) == 1
    assert saved_home["blocks"][0]["id"] == "blk_home_1"

    assert saved_shop["title"] == "Shop Page"
    assert saved_shop["description"] == "Exclusive Merch"
    assert saved_shop["avatar_url"] == "https://cdn.example.com/shop_avatar.png"
    assert saved_shop["theme"]["background_color"] == "#123456"
    assert saved_shop["theme"]["card_style"] == "glass"
    assert len(saved_shop["blocks"]) == 1
    assert saved_shop["blocks"][0]["id"] == "blk_shop_1"

    # 2. Verify get_public_bio_page returns properly filtered and isolated subpages
    pub_res = await get_public_bio_page(handle="multipage_creator", db=db)
    assert len(pub_res["blocks"]) == 1
    assert pub_res["blocks"][0]["id"] == "blk_home_1"
    assert len(pub_res["pages"]) == 2
    pub_shop = next(p for p in pub_res["pages"] if p["id"] == "page_shop")
    assert pub_shop["blocks"][0]["id"] == "blk_shop_1"
    assert pub_shop["avatar_url"] == "https://cdn.example.com/shop_avatar.png"
    assert pub_shop["theme"]["background_color"] == "#123456"


@pytest.mark.asyncio
async def test_upload_bio_avatar(monkeypatch):
    from api.routes.bio_pages import upload_bio_avatar
    from fastapi import UploadFile
    import io

    user = {"user_id": "usr_creator1"}
    monkeypatch.setattr(
        "utils.storage.upload_file_async",
        AsyncMock(return_value="https://cdn.example.com/bio_avatars/avatar_test.png"),
    )

    file = UploadFile(
        filename="profile.jpg",
        file=io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"),
        headers={"content-type": "image/jpeg"},
    )
    res = await upload_bio_avatar(file=file, current_user=user)
    assert "url" in res
    assert res["url"] == "https://cdn.example.com/bio_avatars/avatar_test.png"
    assert res["filename"].startswith("avatar_")
    assert res["filename"].endswith(".jpg")


