import pytest
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from api.routes.bio_pages import (
    _is_block_active,
    BioPageConfig,
    BioBlockItem,
    BioTheme,
    get_my_bio_page,
    save_my_bio_page,
    get_public_bio_page,
    track_bio_link_click,
    subscribe_to_bio_newsletter,
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
